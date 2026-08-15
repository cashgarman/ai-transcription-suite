# Architecture

## The shape of the system

Summit is a single-process desktop application with a command-line entry point
sharing the same core. There is no server, no database, and no IPC. The
"backend" is a set of plain Python modules that the GUI calls on a worker
thread.

```
┌──────────────────────────────────────────────────────────────────┐
│ Presentation                                                     │
│   speaker_transcriber/ui/         PySide6 widgets, dialogs, theme │
│   speaker_transcriber/app.py      GUI bootstrap + splash          │
│   speaker_transcriber/__main__.py CLI                             │
└───────────────────────────┬──────────────────────────────────────┘
                            │  Qt signals (worker → GUI thread)
┌───────────────────────────┴──────────────────────────────────────┐
│ Orchestration                                                    │
│   ui/worker.py                    QThread wrappers               │
│   pipeline/processor.py           stage sequencing, progress      │
│   models/model_manager.py         VRAM, OOM fallback ladder       │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────┴──────────────────────────────────────┐
│ Domain                                                           │
│   audio/        FFmpeg decode, concat, probing                    │
│   models/       transcription, alignment, diarization, notes      │
│   pipeline/     speaker assignment, block merging, types          │
│   prompts/      summary style registry + prompt text              │
│   export/       TXT, MD, JSON, SRT, VTT, CSV, PDF                 │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────┴──────────────────────────────────────┐
│ Infrastructure                                                   │
│   config.py     settings schema + keyring                         │
│   cache/        transcript and speaker-name persistence           │
│   logging_config.py, gpu_stats.py, host_stats.py                  │
│   cuda_setup.py, *_compat.py    third-party workarounds           │
└──────────────────────────────────────────────────────────────────┘
```

The dependency direction is strictly downward. Nothing in `pipeline/`,
`models/`, `audio/`, or `export/` imports from `ui/`, which is what makes the
CLI possible and what keeps the test suite able to exercise the pipeline
without a display.

## Module map

| Package | Responsibility |
|---|---|
| `speaker_transcriber/audio/` | Turn arbitrary media into one mono 16 kHz WAV. `ffmpeg.py` shells out to `ffmpeg`/`ffprobe`, `sources.py` models single- and multi-file inputs, `preprocessing.py` is the context manager that produces the normalised file and cleans up. |
| `speaker_transcriber/models/` | Everything that loads a model. `transcription.py`, `alignment.py`, `diarization.py` are the three inference stages; `model_manager.py` owns VRAM and the OOM fallback ladder; `summarization.py` and `notes_assembly.py` are the notes pipeline; `*_catalog.py` browse and download models. |
| `speaker_transcriber/pipeline/` | The stage sequencer (`processor.py`), the dataclasses that flow between stages (`types.py`), and the two pure algorithms: `speaker_assignment.py` and `transcript_merger.py`. |
| `speaker_transcriber/prompts/` | The summary style registry (a Python package `__init__.py`) plus one directory of prompt text files per style. |
| `speaker_transcriber/export/` | One module per output format, plus a four-module PDF subsystem and a document model for parsed meeting notes. |
| `speaker_transcriber/ui/` | PySide6. One main window, several dialogs, about twenty custom widgets, and the theme. |
| `speaker_transcriber/cache/` | Transcript JSON and speaker display names on disk, so reopening a file does not mean re-transcribing it. |

Standalone modules at the package root handle configuration (`config.py`),
logging (`logging_config.py`), platform metrics (`gpu_stats.py`,
`host_stats.py`), errors (`errors.py`), and a set of compatibility shims for
CUDA, PyTorch, SpeechBrain, and Hugging Face Hub.

## The data model

Five dataclasses in `speaker_transcriber/pipeline/types.py` carry everything
between stages. They are plain, mutable, and have no methods beyond two
conveniences on `TranscriptResult`.

```23:41:speaker_transcriber/pipeline/types.py
@dataclass
class Word:
    word: str
    start: float
    end: float
    speaker: str = "UNKNOWN"
    overlapping_speakers: list[str] = field(default_factory=list)
    uncertain: bool = False


@dataclass
class TranscriptSegment:
    start: float
    end: float
    speaker: str
    text: str
    words: list[Word] = field(default_factory=list)
    overlapping_speakers: list[str] = field(default_factory=list)
    uncertain: bool = False
```

`RawSegment` is what Whisper produces and what WhisperX enriches with word
dictionaries. `DiarizationSegment` is a single pyannote turn: a start, an end,
and a label such as `SPEAKER_00`. `Word` is the unit that speaker assignment
operates on. `TranscriptSegment` is a readable block of one speaker's speech.
`TranscriptResult` is the whole job.

Two fields deserve attention because they are the honest part of the model.
`overlapping_speakers` records other speakers whose diarization turns
intersected a word or block, and `uncertain` marks words where that overlap was
substantial enough that the primary-speaker choice may be wrong. Diarization
picks exactly one speaker per word, but these fields preserve the fact that the
choice was contested, and the JSON exporter writes them out.

`TranscriptResult.speakers` is a mapping from the raw pyannote label to a
display name. Right after processing it holds `{"SPEAKER_00": "Speaker 1", …}`;
after the user renames someone in the speaker table it holds their real name.
Nothing downstream mutates the raw labels, so renaming is always reversible and
the cache can store names separately from the transcript.

## How a transcription run flows

`TranscriptionProcessor.run()` in `speaker_transcriber/pipeline/processor.py`
is the single sequencer. It is a straight-line function, not a framework, and
the whole run is about 250 lines.

Progress is reported against a fixed weight table, so the bar advances at a
plausible rate rather than jumping:

```28:37:speaker_transcriber/pipeline/processor.py
STAGES = {
    "loading_media": (0.00, 0.02),
    "extracting_audio": (0.02, 0.08),
    "loading_whisper": (0.10, 0.05),
    "transcribing": (0.15, 0.35),
    "aligning": (0.50, 0.20),
    "diarizing": (0.70, 0.20),
    "assigning_speakers": (0.90, 0.05),
    "formatting": (0.95, 0.05),
}
```

Each entry is `(base, weight)`; overall progress is
`base + weight × stage_fraction`. Stages emit a `ProgressUpdate` that also
carries elapsed time and current VRAM, which the status strip renders.

The three inference stages are not equal in importance, and the processor
treats them differently:

- **Transcription is required.** If it fails, the run fails.
- **Alignment is optional.** If WhisperX raises, the processor logs a fallback
  decision and continues with segment-level timestamps. Every word in such a
  segment is marked `uncertain=True`, and `alignment_available` stays `False`.
- **Diarization is optional.** If pyannote raises, the processor records
  "Diarization unavailable" and continues with an empty turn list, which leaves
  every word labelled `UNKNOWN`.

This is why a missing Hugging Face token degrades the product rather than
breaking it: you still get a transcript, just without speaker labels.

Cancellation is a `threading.Event` checked at stage boundaries by
`_check_cancel()` and again inside the long-running loops in audio extraction,
transcription, alignment, and diarization. It raises `ProcessingCancelled`. On
the way out, the processor attaches a partial result when it can — if
transcription had finished, you keep the text even though you cancelled during
diarization.

Two guarantees hold on every exit path: `model_manager.clear_cuda()` runs in a
`finally` block, and each inference stage deletes its own model in its own
`finally` block. Between them, VRAM is released whether the run succeeded,
failed, or was cancelled.

## Degradation and recovery

The application assumes the GPU will run out of memory and plans for it in two
independent places.

**The transcription ladder** lives in
`ModelManager.run_transcription_with_fallback()`. On a CUDA OOM it clears the
cache and retries, halving batch size first, then stepping the model down
(`large-v3` → `distil-large-v3` → `medium`) and resetting batch size at each
step. It tracks attempted `(model, batch_size)` pairs so it cannot loop. When
`medium` at batch size 1 still fails, it raises with a message that says so.

**The device ladder** in `run_device_stage_with_fallback()` covers alignment
and diarization, which have no batch size to reduce. It has exactly one rung:
CUDA → CPU.

Meeting notes are handled separately and deliberately not automatically, in
`ui/worker.py` and `ui/oom_recovery_dialog.py`. Silently shrinking the context
window or swapping the model would change the notes the user gets, so the
worker pauses, emits `oom_detected`, and blocks on an event until the GUI thread
returns a choice: lower the context one step, switch to a smaller installed
model, retry unchanged, or stop and keep what was written. The user can tick
"Always use this option" to persist the decision into
`AppSettings.ollama_oom_policy`.

## Threading

The GUI thread never runs inference. Every long operation is a `QThread`
subclass in `speaker_transcriber/ui/worker.py` that emits Qt signals; the main
window connects those signals to slots which are the only code that touches
widgets.

| Worker | Emits |
|---|---|
| `ProcessingWorker` | `progress(ProgressUpdate)`, `completed(TranscriptResult)`, `cancelled(TranscriptResult\|None)`, `failed(str)` |
| `SummarizationWorker` | `progress`, `chunk(str)`, `section_break()`, `completed(str)`, `failed(str)`, `cancelled()`, `oom_detected(OomRecoveryRequest)` |
| `PdfExportWorker` | the summarization signals plus `summary_ready(str)` and `completed(str)` with the output path |
| `OllamaModelListWorker`, `CatalogListWorker`, `CatalogDownloadWorker` | model discovery and downloads |
| `MediaDurationProbeWorker` | `duration_ready(str, float)` so the input timeline can size itself |

Logging crosses the boundary differently. Handlers push `LogRecord`s onto a
`queue.Queue`, and a `QTimer` on the main window drains it every 200 ms into the
log panel. That avoids touching widgets from arbitrary threads without needing
a signal per log line.

## Where the boundaries are drawn

A few decisions shape the codebase more than the rest:

**Sequential model loading, not a model server.** Loading one model at a time
and deleting it costs a few seconds per stage but lets the application run on a
6 GB card. The alternative — keeping models resident — would roughly triple
peak VRAM.

**The prompt system is text files, not templates.** `prompts/__init__.py`
loads `.txt` files verbatim and caches them. There is no placeholder
substitution; dynamic content is wrapped in Markdown headings by the summarizer
in code. This means prompts can be edited and reloaded at runtime (File →
Reload System Prompts) without touching Python, and the test suite can assert on
prompt content directly.

**Two PDF engines behind one function.** `export_meeting_pdf()` dispatches to
ReportLab or WeasyPrint and falls back to the other if the requested one is
unavailable. Both read the same `PdfLayout` and `PdfPalette`, so the same
document comes out either way. WeasyPrint gives better typography; ReportLab
has no native dependencies, so it is the default.

**The cache key is the filename stem.** For a single input file,
`MediaSource.cache_key()` returns the file's stem with no hash of its contents.
Reopening the same file loads instantly, which is the common case, but replacing
a file with different content under the same name will hit a stale cache until
the user re-transcribes. Multi-file inputs do hash paths, sizes, and mtimes.

## Related documents

- [Transcription pipeline](pipeline.md) — the stages in detail, plus the
  assignment and merging algorithms
- [Meeting notes and prompts](notes-and-prompts.md) — the second, LLM-based
  pipeline
- [Export subsystem](export.md) — output formats and the PDF renderers
- [Desktop UI](desktop-ui.md) — the window, its widgets, and the worker bridge
- [Configuration and runtime data](configuration.md) — settings, caches, logs
