# Development guide

## Getting set up

Requires Python 3.11 (3.12 may work; 3.11 is the supported build target),
FFmpeg and ffprobe on `PATH`, and for GPU inference an NVIDIA driver with a
CUDA-enabled PyTorch wheel.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# Run the current CUDA-specific PyTorch command from pytorch.org first.
pip install -e ".[dev]"
```

On Linux, substitute `python3.11 -m venv .venv` and `. .venv/bin/activate`.

Diarization additionally needs a Hugging Face read token with the pyannote model
terms accepted. See the [configuration doc](configuration.md#the-hugging-face-token)
for how the token is resolved and stored.

## Running

| Command | What it does |
|---|---|
| `python app.py` | The GUI |
| `.\scripts\run_windows.bat` / `./scripts/run_linux.sh` | The GUI via the venv |
| `python -m speaker_transcriber INPUT …` | The CLI |
| `speaker-transcriber` / `speaker-transcriber-gui` | Console entry points after install |

`app.py` at the repository root re-executes itself under `.venv` if the
dependencies are missing from the current interpreter, so double-clicking it
works even outside an activated environment.

## Layout of the repository

```
speaker_transcriber/      the application package
  audio/  models/  pipeline/  prompts/  export/  ui/  cache/
  assets/                 icon and bundled font
tests/                    pytest suite, 657 tests
scripts/                  launchers, Windows build, website wrappers
website/                  the Next.js marketing site
docs/                     this documentation
app.py                    GUI launcher
speaker_transcriber.spec  PyInstaller spec
```

A few loose scripts at the root (`scratch_*.py`, `smoke_*.py`, `_preview_*.py`,
`tmp_*.py`) are manual smoke tests kept for convenience. They are not part of
the test suite and are not imported by the package.

## Tests

```bash
python -m pytest
```

657 tests, no model weights downloaded, no network, no display. Transcripts and
diarization timelines are constructed inline, and inference classes are replaced
with fakes. The whole suite runs in seconds.

`tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen`, which lets widget tests
instantiate real `QWidget`s — including the full `MainWindow` — without a
display server. Several UI tests genuinely drive the window rather than mocking
it.

Coverage by area:

| Area | Files |
|---|---|
| Pipeline | `test_processor.py`, `test_speaker_assignment.py`, `test_transcript_merger.py`, `test_remove_speaker.py`, `test_oom_fallback.py` |
| Audio | `test_audio.py`, `test_multi_source.py` |
| Export | `test_exporters.py`, `test_pdf_export.py`, `test_pdf_options.py`, `test_participants.py`, `test_speaker_stats.py` |
| Notes | `test_summarization.py`, `test_notes_assembly.py`, `test_summary_sections.py`, `test_notes_oom_recovery.py`, `test_prompts.py`, `test_prompt_content.py` |
| Catalogs | `test_hf_catalog.py`, `test_ollama_catalog.py`, `test_ollama_models.py` |
| Config and cache | `test_config.py`, `test_transcript_cache.py`, `test_speaker_name_store.py`, `test_speaker_names.py` |
| UI | `test_hazard_progress.py`, `test_notification.py`, `test_text_search.py`, `test_summary_search.py`, `test_progress_tooltips.py`, `test_branding.py` |
| Platform | `test_gpu_stats.py`, `test_host_stats.py` |

`test_prompt_content.py` is worth knowing about. It asserts on the *content* of
prompt files: that no template braces or TODO markers appear, that each file
stays under a character ceiling so prompts cannot crowd out the transcript, and
that specific instructions survive edits. Editing a prompt can fail the suite,
which is intentional — prompts are behaviour.

## Building a Windows executable

```powershell
pip install -e ".[dev]"
.\scripts\build_windows.bat
```

or directly:

```powershell
pyinstaller --clean -y speaker_transcriber.spec
```

Output is a one-folder bundle at `dist\SpeakerTranscriber\SpeakerTranscriber.exe`.
Distribute the whole folder, not just the executable.

The spec bundles:

- **Hidden imports** — all submodules of `faster_whisper`, `whisperx`,
  `pyannote`, and `speechbrain`, which PyInstaller cannot discover statically,
  plus `keyring.backends.Windows` and `reportlab`.
- **Data** — package data from whisperx, pyannote.audio, faster_whisper, and
  reportlab, plus `speaker_transcriber/prompts/` and
  `speaker_transcriber/assets/`.
- **Binaries** — `ctranslate2` and `torch` dynamic libraries, and on Windows the
  `nvidia.cudnn`, `nvidia.cublas`, and `nvidia.cuda_nvrtc` DLLs.
- **A runtime hook**, `pyi_rth_cuda.py`, which calls
  `configure_cuda_libraries()` before anything else imports, so the NVIDIA DLLs
  are on `PATH` and registered with `os.add_dll_directory()` in time for
  CTranslate2 to find them.

Excluded: `tkinter`, `customtkinter`, `IPython`, `jupyter`, `notebook`.

The build is windowed (`console=False`) with `assets/summit.ico` as the icon,
and UPX is off.

Two things are deliberately not bundled. **Model weights** are downloaded on
first use into the normal caches, which keeps the distribution from being tens
of gigabytes and lets models be shared with other tools. **FFmpeg** must be
installed separately, since redistributing it carries licensing obligations.

## Conventions

**Allman brace style** in languages that use braces. Python has none, so this
mainly applies to the TypeScript in `website/`.

**Split render from write in exporters.** Every exporter has a `render_*`
returning a string and an `export_*` writing it, so tests assert on strings and
never touch the filesystem.

**Never import `ui` from below.** Nothing in `pipeline`, `models`, `audio`,
`export`, or `prompts` may import from `speaker_transcriber.ui`. That rule is
what keeps the CLI working and the tests headless.

**Widgets only on the GUI thread.** Workers emit signals; slots touch widgets.
If a worker needs an answer from the user, use the blocking-event handshake in
`NotesMemoryRecoveryMixin` rather than reaching for a widget.

**Persist deviations, not state,** for option dictionaries, so that adding an
option does not need a settings migration.

## Where to make common changes

| Change | Files |
|---|---|
| Add an export format | `export/<name>_exporter.py`, register in `export/__init__.py`, extend `tests/test_exporters.py` |
| Add a summary style | New directory under `prompts/styles/` with all five `.txt` files, an entry in `SUMMARY_STYLES`, a layout in `pdf_layout.py`, an accent pair in `STYLE_ACCENTS` |
| Add a PDF theme | A palette constant and a registry entry in `pdf_theme.py`; `tests/test_pdf_options.py` will check invariants automatically |
| Add a PDF option | A `PdfOption` in `pdf_options.py` and its effect in `apply_pdf_options()`; the dialog picks it up |
| Add a setting | A field on `AppSettings`, validation in `validate()`, and a control in the relevant dialog |
| Change a colour | `ui/theme.py` for the app, `export/pdf_theme.py` for documents, `website/app/globals.css` for the site — see the [design system](design-system.md) |
| Add a pipeline stage | An entry in `STAGES` in `pipeline/processor.py` (weights must still total 1.0) and a call site in `run()` |

## Known rough edges

- **Single-file cache keys ignore content.** Replacing a file in place under the
  same name hits a stale cached transcript. Re-transcribing or clearing
  `use_cached_transcript` works around it; hashing the file would fix it at the
  cost of a read on every open.
- **`debug_log.py` is not redacted.** It writes `debug-4ba2aa.log` to the
  project root with no rotation. It is a development aid; treat the file as
  sensitive and do not ship it.
- **No timeout on the Ollama client.** A hung local model blocks the
  summarisation worker until cancelled.
- **The website has no OG image**, so link previews are text-only.
- **Prompt edits can fail tests** by design; see `test_prompt_content.py`.

## Documentation map

- [Architecture](architecture.md)
- [Transcription pipeline](pipeline.md)
- [Meeting notes and prompts](notes-and-prompts.md)
- [Export subsystem](export.md)
- [Desktop UI](desktop-ui.md)
- [Design system](design-system.md)
- [Configuration and runtime data](configuration.md)
- [Marketing website](website.md)
