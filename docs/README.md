# Speaker Transcriber / Summit — Documentation

This folder documents the codebase and the design of the whole project: the
Python desktop application, its inference pipeline, its export subsystem, and
the separate Next.js marketing website.

The product ships under two names. `speaker-transcriber` is the Python
distribution and the CLI entry point; **Summit** is the name shown to users in
the window title, the splash screen, the taskbar identity, and on the website.
Both refer to the same application.

## Start here

| If you want to… | Read |
|---|---|
| Understand how the whole system fits together | [Architecture](architecture.md) |
| Work on transcription, alignment, or diarization | [Transcription pipeline](pipeline.md) |
| Work on AI meeting notes, prompts, or Ollama | [Meeting notes and prompts](notes-and-prompts.md) |
| Add an export format or change PDF output | [Export subsystem](export.md) |
| Work on the desktop window, widgets, or threading | [Desktop UI](desktop-ui.md) |
| Change a colour, font, or spacing value anywhere | [Design system](design-system.md) |
| Change settings, caching, logging, or secrets | [Configuration and runtime data](configuration.md) |
| Work on the marketing site | [Marketing website](website.md) |
| Position, price, launch, or sell Summit | [Marketing plan](marketing-plan.md) |
| Run tests, build an executable, or use the CLI | [Development guide](development.md) |
| See known defects and what to fix next | [Code review](code-review.md) |

## What the application does

Summit takes an audio or video recording and produces a transcript in which
every word carries a timestamp and a speaker label, entirely on the user's own
machine. It can then write meeting notes from that transcript using a local
language model. No audio, transcript, or notes content is ever sent to a remote
service. The only network traffic is model downloading, and that stops once the
models are cached.

The processing chain is:

```
media file(s)
   → FFmpeg          mono 16 kHz PCM WAV
   → faster-whisper  segment-level text
   → WhisperX        word-level timestamps
   → pyannote.audio  speaker turns
   → assignment      each word gets a speaker
   → merging         readable speaker-labelled blocks
   → export          TXT / MD / JSON / SRT / VTT / CSV
   → Ollama          meeting notes → PDF
```

Only one model is resident in VRAM at a time. Each stage loads its model, runs,
deletes the model, and clears the CUDA cache before the next stage begins.

## Conventions used in these documents

Values quoted here (colour hex codes, default settings, prompt style IDs, field
names) were read from the source at the time of writing and are meant to be
exact. Where a document states a default, that default lives in code and the
code is authoritative; the file and symbol are named so you can check.

File paths are given relative to the repository root. Python module paths use
dots, for example `speaker_transcriber.pipeline.processor`.
