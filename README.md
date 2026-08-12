# Speaker Transcriber

Speaker Transcriber is a private, local desktop and command-line application for
transcribing audio or video, producing accurate word timestamps, and labelling
speaker turns. Audio never leaves the computer.

The inference pipeline loads one model at a time:

1. FFmpeg converts the input to mono 16 kHz PCM WAV.
2. faster-whisper transcribes with CTranslate2.
3. WhisperX aligns words with a language-specific wav2vec2 model.
4. pyannote.audio detects speaker turns.
5. The application assigns each word to a speaker, preserves overlap metadata,
   and creates readable transcript blocks.
6. The Whisper, alignment, and diarization models are deleted between stages
   and the CUDA cache is cleared.

## Diarization and identification

Speaker **diarization** answers “who spoke when?” by grouping similar voices as
`SPEAKER_00`, `SPEAKER_01`, and so on. It does not know a person’s real identity.
Speaker **identification** compares voices with enrolled identities; this
application does not do that. You can rename diarization labels after processing.

## Features

- PySide6 desktop interface with file picker and drag-and-drop
- Responsive worker thread, cancellation, stage progress, elapsed time, and VRAM
- `medium`, `distil-large-v3`, and `large-v3` Whisper models
- Automatic or manual language selection
- Automatic, exact, minimum, or maximum speaker counts
- Word-level timestamps with segment-level fallback when alignment fails
- Speaker-labelled TXT, Markdown, JSON, SRT, WebVTT, and CSV exports
- Overlapping and uncertain regions retained in JSON
- Automatic CUDA OOM fallback: reduce batch, reduce model, then move alignment
  or diarization to CPU
- Optional local Qwen summarization through Ollama
- Rotating local logs with token redaction

## Supported input

MP4, MKV, MOV, AVI, WebM, WAV, MP3, M4A, FLAC, OGG, Opus, and AAC are supported
when the installed FFmpeg build can decode them.

## Requirements

- Windows 10/11 or Linux
- Python 3.11 (3.12 may work, but the supported build target is 3.11)
- FFmpeg and ffprobe on `PATH`
- NVIDIA GPU with a current driver and 6–10 GB VRAM
- CUDA-enabled PyTorch
- Internet access for the initial model downloads only
- A Hugging Face account and read token for pyannote

CPU transcription can be selected from the CLI, but it is substantially slower.

### Expected peak VRAM

Models run sequentially, so these figures are not additive:

| Stage | Typical peak |
|---|---:|
| `medium`, INT8/mixed | 2–4 GB |
| `distil-large-v3`, INT8/mixed | 3–5 GB |
| `large-v3`, INT8/mixed | 5–9 GB |
| WhisperX alignment | 1–2 GB |
| pyannote diarization | 2–4 GB |

Values vary by driver, audio length, batch size, and dependency versions.
`distil-large-v3`, `int8_float16`, and batch size 4 are the defaults.

## Windows installation

Install [Python 3.11](https://www.python.org/downloads/),
[FFmpeg](https://ffmpeg.org/download.html), and an NVIDIA driver. Confirm:

```powershell
py -3.11 --version
ffmpeg -version
nvidia-smi
```

Create an environment and install the CUDA-enabled PyTorch build recommended by
the [PyTorch installer](https://pytorch.org/get-started/locally/), followed by
the project:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# Run the current CUDA-specific PyTorch command from pytorch.org here.
pip install -e ".[dev]"
```

Run the GUI:

```powershell
.\scripts\run_windows.bat
```

## Linux installation

Install FFmpeg, Python 3.11, a supported NVIDIA driver, and the CUDA-enabled
PyTorch wheel recommended by PyTorch:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
# Run the current CUDA-specific PyTorch command from pytorch.org here.
pip install -e ".[dev]"
chmod +x scripts/run_linux.sh
./scripts/run_linux.sh
```

The CUDA toolkit does not usually need to be installed separately when using
PyTorch wheels, but the NVIDIA driver must support the CUDA runtime bundled with
that wheel.

## Hugging Face and pyannote setup

1. Create a read token at
   [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
2. Accept the terms at
   [https://huggingface.co/pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1).
3. If prompted by the model dependency, also accept
   [https://huggingface.co/pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0).
4. Set `HF_TOKEN`, copy `.env.example` to `.env`, or enter the token in the
   Settings dialog.

```powershell
$env:HF_TOKEN = "hf_your_read_token"
```

The Settings dialog stores its token in the operating system credential store.
The token is not stored in the main settings file and is redacted from logs.
The CLI `--hf-token` option is available, but an environment variable is safer
because command arguments may be visible to other local processes.

## GUI usage

1. Start the GUI with `python app.py` or a launcher script.
2. Drop a media file onto the window or click **Browse**.
3. Select the model, language, and speaker-count mode.
4. Adjust batch size, compute type, stage devices, output directory, merge gap,
   and Hugging Face token in **Settings**.
5. Click **Start**. Cancellation occurs at the next safe boundary; FFmpeg is
   terminated immediately when possible.
6. Rename speakers in the right-hand table and click **Apply names**.
7. Click **Export** and select one or more output formats.

If cancellation happens after transcription, the application preserves a
partial plain transcript when practical.

## CLI usage

```bash
python -m speaker_transcriber input.mp4 \
  --model distil-large-v3 \
  --language auto \
  --min-speakers 2 \
  --max-speakers 4 \
  --output ./output \
  --formats txt,json,srt
```

All options:

```text
--model medium|distil-large-v3|large-v3
--device cuda|cpu
--compute-type int8_float16|float16|int8|float32
--batch-size N
--language auto|LANGUAGE_CODE
--num-speakers N
--min-speakers N
--max-speakers N
--alignment-device cuda|cpu
--diarization-device cuda|cpu
--output DIRECTORY
--formats txt,md,json,srt,vtt,csv
--hf-token TOKEN
--verbose
```

Do not combine `--num-speakers` with minimum/maximum speaker counts.

## Settings and logs

Non-secret settings are stored in:

- Windows: `%APPDATA%\SpeakerTranscriber\settings.json`
- Linux: `~/.config/speaker_transcriber/settings.json`

Rotating logs are in the adjacent `logs` directory. They include application,
Python, PyTorch, CUDA, GPU, VRAM, selected models, stage durations, fallback
decisions, and exceptions. Hugging Face tokens are filtered.

## Lowering memory use

1. Use `distil-large-v3` or `medium`.
2. Reduce batch size from 4 to 2 or 1.
3. Keep `int8_float16` on CUDA.
4. Run alignment or diarization on CPU in Settings.
5. Close games, browsers using GPU acceleration, and other model servers.
6. Process with Ollama only after transcription; do not run its model
   concurrently on a constrained GPU.

The pipeline automatically retries CUDA OOM failures. It halves batch size,
falls from `large-v3` to `distil-large-v3`, then to `medium`, and can move
alignment and diarization to CPU. The selected fallback is shown in the log.

## Troubleshooting

**FFmpeg not installed**

Install FFmpeg, ensure both `ffmpeg` and `ffprobe` are on `PATH`, then restart.

**CUDA unavailable**

Confirm `nvidia-smi` works and `python -c "import torch; print(torch.cuda.is_available())"`
prints `True`. Reinstall the CUDA-enabled PyTorch wheel, not the CPU wheel.

**Unsupported or insufficient GPU**

Update the NVIDIA driver, use `medium`, batch size 1, or CPU stage settings.
Cards without suitable CUDA support cannot use GPU inference.

**CUDA out of memory**

Close other GPU programs, lower model/batch size, or move alignment/diarization
to CPU. The application performs these fallbacks automatically where possible.

**Hugging Face authentication or access denied**

Verify the token has read permission and accept all model terms using the same
Hugging Face account.

**Invalid media, corrupt audio, or no speech**

Confirm FFmpeg can decode the file and that an audible speech track exists.

**Alignment failed**

The transcript continues with segment-level timestamps. Some languages do not
have a supported alignment model.

**Diarization failed**

The plain transcript remains exportable with `UNKNOWN` speaker labels.

## Tests

Tests use mocked transcripts and timelines and do not download model weights:

```bash
python -m pytest
```

Coverage includes overlapping turns, gaps, multiple speakers within one Whisper
segment, unknown speakers, merging, exporters, settings, processor cancellation,
and CUDA fallback decisions.

## PyInstaller

Build from the configured Python 3.11 environment:

```powershell
pip install -e ".[dev]"
.\scripts\build_windows.bat
```

Or manually:

```powershell
pyinstaller --clean -y speaker_transcriber.spec
```

The one-folder output is `dist\SpeakerTranscriber\SpeakerTranscriber.exe`. Distribute the
entire `dist\SpeakerTranscriber` folder, not just the `.exe`. CUDA and AI dependencies
make the distribution large. Model weights are not bundled; they are downloaded
to the normal local caches on first use. FFmpeg must still be installed separately.

## Privacy and limitations

All audio decoding and inference is local. The application does not send audio
or transcript content to an API. Hugging Face is contacted only to authenticate
and download model files; Ollama summarization is local.

Diarization is probabilistic, not identity recognition. Similar voices, short
interjections, crosstalk, music, reverberation, background noise, and telephone
audio can reduce accuracy. Overlapping pyannote turns are retained, and JSON
records secondary speakers and uncertainty, but one primary speaker is still
chosen per word. Forced alignment may omit timestamps for words it cannot map.
