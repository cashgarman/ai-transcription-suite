# Transcription pipeline

This document covers everything from a media file on disk to a
`TranscriptResult`: audio normalisation, the three inference stages, and the two
algorithms that turn word timings and speaker turns into readable blocks.

For the second pipeline — the one that writes meeting notes from a finished
transcript — see [Meeting notes and prompts](notes-and-prompts.md).

## Input handling

### Supported formats

`speaker_transcriber/audio/ffmpeg.py` gates input on file extension before
FFmpeg is ever invoked:

- **Audio** — `.aac`, `.flac`, `.m4a`, `.mp3`, `.ogg`, `.opus`, `.wav`
- **Video** — `.avi`, `.mkv`, `.mov`, `.mp4`, `.webm`

Whether a given file actually decodes depends on the installed FFmpeg build.

### One input or several

`MediaSource` in `speaker_transcriber/audio/sources.py` models the input as a
tuple of paths regardless of how many there are. `MediaSource.parse()` accepts a
single path or a list; `validate()` checks that each file exists and has a
supported extension.

Multi-file input exists so that a meeting split across several recordings can be
processed as one job. The files are extracted individually, then concatenated,
and the pipeline sees a single continuous WAV. Speaker diarization therefore
runs across the whole meeting, which is the point — the same person keeps the
same label across file boundaries.

The GUI supports multi-file input through the input timeline, where files can be
reordered by dragging. The CLI takes a single positional path.

### Cache key

`MediaSource.cache_key()` derives the key used by the transcript cache and the
speaker-name store:

```68:70:speaker_transcriber/audio/sources.py
    def cache_key(self) -> str:
        ordered = tuple(sorted(self.paths, key=lambda item: str(item)))
        return f"{ordered[0].stem}_{_fingerprint(ordered)}"
```

`_fingerprint()` hashes each path together with its modification time and size,
so a recording is identified by where it lives and what it contains rather than
by its filename alone. Two files named `meeting.mp4` in different folders get
different keys, and replacing a file's contents invalidates its cached
transcript. A file that has been moved or deleted falls back to a path-only
digest instead of raising.

Single-file sources were once keyed on the bare stem, which collided across
folders and served stale transcripts after a file was replaced in place. The
transcript cache migrates those older entries the first time it sees the
recording, renaming them onto the new key — but only when the cached
transcript's recorded `source_file` resolves to the same file, so a colliding
entry belonging to a different recording is left alone. See
`TranscriptCache._adopt_legacy_files`.

## Audio normalisation

Every downstream stage expects mono 16 kHz PCM. `normalized_media()` in
`speaker_transcriber/audio/preprocessing.py` is a context manager that produces
that file in a temporary directory and removes the directory on exit.

**Probing** runs first, per file:

```
ffprobe -v error -show_entries format=duration:stream=codec_type -of json <path>
```

It fails with `MediaError` if the file has no audio stream or a non-positive
duration. For multi-file input, durations are summed.

**Extraction** is one FFmpeg call per input file:

```
ffmpeg -hide_banner -nostdin -y -i <source> -vn -ac 1 -ar 16000 \
       -c:a pcm_s16le -progress pipe:1 -nostats <destination>
```

`-progress pipe:1` makes FFmpeg emit `out_time_ms=` lines on stdout, which the
extractor parses and divides by the known duration to drive the progress bar.
This is why the extraction stage has real progress rather than a spinner.

Cancellation during extraction terminates the FFmpeg process, waits three
seconds, then kills it, and raises `ProcessingCancelled`. This is the one place
where cancellation is immediate rather than deferred to the next stage boundary.

**Concatenation** applies only to multi-file input. Chunks are written as
`chunk_000.wav`, `chunk_001.wav`, and so on, listed in a `concat_list.txt`, and
joined with:

```
ffmpeg -hide_banner -nostdin -y -f concat -safe 0 -i <list> -c copy <destination>
```

Because every chunk was already normalised to the same format, `-c copy` is a
byte copy with no re-encoding. A single chunk skips FFmpeg entirely and is
copied directly. Progress across chunks is weighted by each chunk's duration, so
a long file does not advance at the same rate as a short one.

## Stage 1 — Transcription

`Transcriber.transcribe()` in `speaker_transcriber/models/transcription.py`
wraps faster-whisper, which runs Whisper through CTranslate2.

It loads `WhisperModel(model, device, compute_type)` and wraps it in
`BatchedInferencePipeline`, then calls:

```python
batched_model.transcribe(
    path, batch_size=..., language=..., word_timestamps=False, vad_filter=True
)
```

Word timestamps are explicitly off here. Whisper's own word timings are less
accurate than forced alignment, so the next stage produces them instead. VAD
filtering is on, which drops silence and shortens the work.

Three behaviours are worth knowing:

- If CUDA is requested but unavailable, it raises a `RuntimeError` that tells
  the user to install the CUDA-enabled PyTorch wheel, rather than silently
  running on CPU at a fraction of the speed.
- On CPU, `int8_float16` is not supported, so the compute type is silently
  coerced to `int8`.
- If Whisper returns no non-empty segments, it raises `NoSpeechError` rather
  than producing an empty transcript.

The detected language comes back on the info object and is stored on the result,
which matters because the alignment stage needs it to choose a model.

Output is a list of `RawSegment` with text and segment-level times, no words.

## Stage 2 — Alignment

`Aligner.align()` in `speaker_transcriber/models/alignment.py` uses WhisperX to
force-align the transcript against the audio with a language-specific wav2vec2
model, producing per-word start and end times.

```python
model, metadata = whisperx.load_align_model(language_code=..., device=...)
audio = whisperx.load_audio(str(audio_path))
result = whisperx.align(segments, model, metadata, audio, device,
                        return_char_alignments=False)
```

When `alignment_model` is `"auto"` — the default — the `model_name` argument is
omitted and WhisperX picks its default model for the detected language. A
specific model can be set in the UI or with `--alignment-model`.

Alignment is the stage most likely to fail benignly. Not every language has a
supported alignment model, and forced alignment can fail to map some words. When
the stage raises, the processor keeps the unaligned `RawSegment` list and
carries on. Each such segment becomes a single `Word` spanning the whole segment
with `uncertain=True`, so the transcript stays usable and the JSON records the
reduced confidence.

## Stage 3 — Diarization

`Diarizer.diarize()` in `speaker_transcriber/models/diarization.py` runs a
pyannote.audio pipeline, by default `pyannote/speaker-diarization-3.1`.

This is the only stage that needs credentials. A Hugging Face read token is
required, and the account must have accepted the terms for the pyannote models.
Without a token the stage raises `AuthenticationError`.

Four compatibility shims are applied before the pipeline loads, because pyannote
and its dependencies lag behind their upstreams:

| Shim | Problem it solves |
|---|---|
| `configure_huggingface_client()` | Installs httpx clients with 5 retries; honours `HF_HUB_INSECURE_SSL` for corporate TLS interception |
| `patch_hf_hub_use_auth_token()` | pyannote passes the removed `use_auth_token=` argument; this maps it to `token=` |
| `patch_torch_load_weights_only()` | PyTorch 2.x defaults `torch.load(weights_only=True)`, which rejects pyannote's Lightning checkpoints |
| `patch_speechbrain_lazy_modules()` | SpeechBrain's lazy module `__getattr__` calls `inspect.stack()` and eagerly imports optional integrations |

Pipeline loading retries up to five times with exponential backoff capped at 30
seconds, but only for retryable failures — HTTP 429 and 5xx, connection resets,
TLS errors, and timeouts. A 404 or a gated-repo error is not retried, because
retrying will not help.

Speaker count is passed through as either `num_speakers` (exact) or
`min_speakers`/`max_speakers`, never both. The processor rejects that
combination during validation.

Output is a list of `DiarizationSegment` sorted by `(start, end, speaker)`.

### Prefetching

When a token is available, the processor calls `prefetch_diarization_models()`
during the `loading_media` stage, before any GPU work starts. This pulls the
pipeline config, segmentation model, and embedding model. It means a
download failure surfaces in the first two percent of the run rather than
seventy percent of the way through, after Whisper has already spent minutes on
the audio.

## Stage 4 — Speaker assignment

`speaker_transcriber/pipeline/speaker_assignment.py` decides which speaker said
each word. It is pure geometry over intervals with no model involved.

For a word spanning `[start, end]`, with `midpoint = (start + end) / 2`:

1. Compute `overlapping` — every diarization turn that intersects the word at
   all — and `containing` — every turn whose span contains the midpoint.
2. **If any turn contains the midpoint**, pick the one maximising
   `(overlap_amount, -turn_duration)`. Most overlap wins; ties break toward the
   *shorter* turn.
3. **Otherwise, if any turn merely overlaps**, pick the one with the most
   overlap.
4. **Otherwise**, find the nearest turn by edge distance. Use it only if that
   distance is within `inherit_speaker_threshold_seconds` (default 0.3). If it
   is further, the word stays `UNKNOWN`.

The tie-break toward shorter turns in step 2 is the interesting choice. When a
short interjection sits inside a long turn from another speaker, both contain
the midpoint; preferring the shorter one attributes the interjection to the
person who actually made it rather than absorbing it into the surrounding
monologue.

Step 4 exists because alignment and diarization disagree at boundaries. A word
whose timing places it just outside every turn is almost always a boundary
artefact, so inheriting from a turn 0.3 s away is right far more often than
labelling it `UNKNOWN`. Beyond that threshold, honesty wins.

Afterwards the word records the other speakers it overlapped in
`overlapping_speakers`, and is flagged `uncertain` if any of them overlapped it
by at least 50 % of its duration.

Words are produced from segments by `words_from_segments()`. If a segment has
aligned words, each becomes a `Word`. If it does not — because alignment failed
— the whole segment becomes one `Word` marked `uncertain=True`.

## Stage 5 — Merging into blocks

`speaker_transcriber/pipeline/transcript_merger.py` groups the labelled word
stream into readable blocks. A word joins the current block only if all three
conditions hold:

1. Its speaker matches the block's speaker.
2. The gap from the previous word's end is at most `merge_gap_seconds`
   (default 0.5).
3. The resulting block would not exceed `max_block_duration_seconds`
   (default 30.0).

Otherwise the block is flushed and a new one starts. A speaker change always
splits, which is what makes the transcript readable as dialogue. The duration
cap keeps a single uninterrupted monologue from becoming one unscrollable
paragraph.

Text is joined with spaces and then cleaned up: a space before punctuation is
removed, and a space after an opening bracket is removed. The block inherits the
union of its words' `overlapping_speakers` (minus its own) and is `uncertain` if
any of its words is.

Finally the processor builds the display-name map by sorting the unique
non-`UNKNOWN` speaker IDs and numbering them `Speaker 1`, `Speaker 2`, and so on.

## Error taxonomy

`speaker_transcriber/errors.py` defines a small hierarchy, all descending from
`SpeakerTranscriberError`, which the CLI catches as a group.

| Exception | Raised when |
|---|---|
| `ProcessingCancelled` | The cancel event was observed at a safe boundary. Carries an optional `partial_result`. |
| `MediaError` | Missing or unsupported file, ffprobe/ffmpeg failure, no audio stream, zero duration, concat failure. |
| `AuthenticationError` | Diarization with no token, or a Hugging Face 401/403/gated-repo response. |
| `NoSpeechError` | Whisper produced no non-empty segments. |

Three other exception types propagate without being part of the taxonomy:
`ValueError` from option validation, and `RuntimeError` for CUDA unavailability,
exhausted OOM fallbacks, and unrecoverable Hugging Face failures.

## Command-line interface

`python -m speaker_transcriber INPUT [options]` runs the same pipeline without
Qt. It applies the same startup shims as the GUI, prints progress to stderr as
`NNN% message [VRAM used/total MB]` (only when the percentage changes), and
prints exported paths to stdout.

| Option | Default | Notes |
|---|---|---|
| `INPUT` | required | One media file |
| `--model` | `distil-large-v3` | Any faster-whisper model ID |
| `--device` | `cuda` | `cuda` or `cpu` |
| `--compute-type` | `int8_float16` | Also `float16`, `int8`, `float32` |
| `--batch-size` | `4` | Must be at least 1 |
| `--language` | `auto` | Or an explicit language code |
| `--num-speakers` | none | Cannot be combined with min/max |
| `--min-speakers` / `--max-speakers` | none | Min must not exceed max |
| `--alignment-device` / `--diarization-device` | `cuda` | Per-stage device |
| `--alignment-model` | `auto` | |
| `--diarization-model` | `pyannote/speaker-diarization-3.1` | |
| `--output` | `output` | Export directory |
| `--formats` | `txt,json` | Comma-separated from `txt,md,json,srt,vtt,csv` |
| `--hf-token` | none | Prefer the `HF_TOKEN` environment variable |
| `--verbose` | off | DEBUG-level logging |

Exit codes: `0` success, `1` a known error (`SpeakerTranscriberError`,
`ValueError`, `OSError`), `2` an unexpected exception or an argparse error,
`130` cancelled or interrupted.

The token resolution order is the same as the GUI: the explicit `--hf-token`
argument, then `HF_TOKEN` from the environment or `.env`, then the OS keyring.
Passing a token as a command argument is less safe than the environment,
because arguments are visible to other local processes.
