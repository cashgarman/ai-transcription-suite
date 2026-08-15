# Desktop UI

The interface is PySide6 (Qt 6), dark-only, and built entirely in code — there
are no `.ui` files. It lives in `speaker_transcriber/ui/`, about twenty widget
modules plus one large `main_window.py`.

For colours, fonts, and spacing values, see the
[design system](design-system.md).

## Startup

`speaker_transcriber/app.py` runs a deliberately staged startup, because
importing torch, whisperx, and pyannote takes several seconds and a window that
appears instantly but does nothing is worse than a splash screen.

1. `configure_process_identity()` sets the Windows AppUserModelID
   `SpeakerTranscriber.Summit` so the taskbar groups and icons correctly.
2. High-DPI rounding policy is set to `PassThrough` before `QApplication` is
   constructed — it has no effect afterwards.
3. `QApplication` is created; organisation name `SpeakerTranscriber`.
4. `apply_application_identity()` sets the display name **Summit** and the
   window icon.
5. `apply_application_theme()` installs the Fusion style, the palette, the
   global stylesheet, and dark window chrome.
6. A frameless 460 × 236 `SplashScreen` appears.
7. `BootstrapWorker`, a `QThread`, does the slow work and reports progress:

| Progress | Phase |
|---|---|
| 0.15 | CUDA library paths, Hugging Face client, PyTorch and SpeechBrain patches |
| 0.45 | `SettingsStore`, logging queue, system information |
| 0.60 | `load_prompts()` |
| 0.75 | Import `MainWindow` |
| 0.90 | Construct the window |
| 1.00 | Ready; splash hands off to the window |

The main thread blocks on a `QEventLoop` until the worker finishes, which keeps
the splash painting and responsive. A bootstrap failure closes the splash, shows
a critical message box, and exits with code 1 — the window is never shown in a
half-initialised state.

Importing `MainWindow` is itself a bootstrap phase because that import pulls in
the pipeline modules, and therefore torch.

## Window layout

```
┌─ Menu bar ─────────────────────────────────────────────────────────────┐
│ File: Recent Files… | Reload System Prompts | Quit (Ctrl+Q)            │
├─ CollapsibleSection "Setup" (expanded) ────────────────────────────────┤
│  InputTimelineWidget                    [Add files…] [Remove selected] │
│  Transcribe │ Align │ Diarize │ Notes │ Style │ PDF │ Notes context    │
│  Language              Speakers (Automatic / Exact / Min–Max)          │
├─ Action row ───────────────────────────────────────────────────────────┤
│ Start  Re-transcribe  Cancel  Settings…  ⟨stretch⟩                     │
│                       Summarize  Cancel  Export PDF…  Export…          │
├─ Status strip ─────────────────────────────────────────────────────────┤
│ HazardProgressBar + stage label + %   Elapsed   CPU RAM VRAM GPU       │
├─ Splitter (4 : 1) ─────────────────────────────────────────────────────┤
│ DetachableTabWidget                   │ Speakers                       │
│   Transcript → TranscriptPanel        │  Label │ Display name │ Spoke  │
│   Summary    → SearchableTextPanel    │  First  Prev  Next  Last       │
├─ CollapsibleSection "Error and processing log" (collapsed) ────────────┤
│ read-only QPlainTextEdit                                               │
└────────────────────────────────────────────────────────────────────────┘
        NotificationBanner floats at top-centre over the central widget
```

The Setup section collapses because it is only needed before a run. The log
section starts collapsed because it is only needed when something goes wrong.

The model row uses stacked captions above each combo box, and the caption for
the currently running stage is highlighted as the pipeline advances
(`_set_active_stage_column()`). The mapping is: `transcribe` → Transcribe audio,
`align` → Align word timestamps, `diarize` → Detect speakers, `summarize` →
Write meeting notes, `pdf` → Format PDF notes. It turns the setup row into a
progress indicator, so the connection between "what I chose" and "what is
happening" stays visible.

## The worker bridge

Nothing on a worker thread touches a widget. Workers are `QThread` subclasses in
`ui/worker.py` that emit signals; the main window's slots do all UI mutation.

| Worker | Signals |
|---|---|
| `ProcessingWorker` | `progress(ProgressUpdate)`, `completed(TranscriptResult)`, `cancelled(TranscriptResult\|None)`, `failed(str)` |
| `SummarizationWorker` | `progress(SummarizationProgress)`, `chunk(str)`, `section_break()`, `completed(str)`, `failed(str)`, `cancelled()`, `oom_detected(OomRecoveryRequest)` |
| `PdfExportWorker` | the above plus `summary_ready(str)` and `completed(str)` carrying the output path |
| `OllamaModelListWorker` | `completed(list)`, `failed(str)` |
| `CatalogListWorker` | `completed(list)`, `failed(str)` |
| `CatalogDownloadWorker` | `progress(DownloadProgress)`, `model_finished(str)`, `failed(str)`, `completed()` |
| `MediaDurationProbeWorker` | `duration_ready(str, float)`, `failed(str, str)` |

Cancellation sets a `threading.Event` the pipeline polls. It is cooperative, so
it takes effect at the next checkpoint rather than instantly — except during
FFmpeg extraction, where the process is terminated directly.

### The OOM handshake

`NotesMemoryRecoveryMixin` implements a round trip from worker to GUI and back,
which Qt signals alone cannot do because they are one-way:

1. The worker catches `OllamaOutOfMemoryError` and emits
   `oom_detected(OomRecoveryRequest)`.
2. The worker blocks on a `threading.Event`.
3. The GUI thread runs `_on_notes_out_of_memory()`, which either applies a saved
   policy or shows `GpuMemoryRecoveryDialog`.
4. The GUI calls `worker.provide_recovery(choice)`, setting the event.
5. The worker wakes, adjusts context or model, and retries.

### Logging

Log handlers push records onto a `queue.Queue`. A `QTimer` drains it into the log
panel every 200 ms. A second `QTimer` polls CPU, RAM, VRAM, and GPU utilisation
every 1000 ms for the status strip.

## Widgets

| Widget | File | What it does |
|---|---|---|
| `InputTimelineWidget` | `input_timeline.py` | Horizontal bar of source files sized by duration, drag to reorder, multi-select |
| `TranscriptView` | `transcript_view.py` | Rich-text transcript with speaker colouring, per-speaker filtering, keyboard navigation |
| `TranscriptTimelineHeatmap` | `transcript_heatmap.py` | 14 px vertical strip showing speaker activity over the recording; click to scroll |
| `TranscriptPanel` | `transcript_panel.py` | Composes the search bar, view, heatmap, and busy overlay |
| `TextFinder` / `TextSearchBar` / `SearchableTextPanel` | `text_search.py` | Case-insensitive search with match count and prev/next |
| `DetachableTabWidget` | `detachable_tab_widget.py` | Tabs that detach into floating windows |
| `CollapsibleSection` | `collapsible_section.py` | Chevron-toggled panel |
| `HazardProgressBar` | `hazard_progress.py` | Animated diagonal-stripe progress bar |
| `BusySpinner` / `BusySpinnerOverlay` | `busy_spinner.py` | Rotating accent arc, optionally over a translucent overlay |
| `NotificationBanner` | `notification.py` | Queued top-centre toasts in four kinds |
| `ModelComboBox` | `model_combo.py` | Two-column model picker with an "Add Models…" sentinel item |
| `SplashScreen` | `splash.py` | Frameless startup splash |
| `BrandMark` | `branding.py` | Paints the Summit logo |
| `ElidedLabel` | `main_window.py` | Single-line label with elision and an active-state background |

`ollama_model_combo.py` is a re-export shim over `model_combo.py`.

## Dialogs

| Dialog | File | Writes |
|---|---|---|
| `SettingsDialog` | `settings_dialog.py` | `compute_type`, `batch_size`, `alignment_device`, `diarization_device`, `merge_gap_seconds`, `max_block_duration_seconds`, `inherit_speaker_threshold_seconds`, `output_directory`, `use_cached_transcript`, and the HF token to the credential store |
| `PdfOptionsDialog` | `pdf_options_dialog.py` | `pdf_theme`, `pdf_options` |
| `SummarySectionsDialog` | `summary_sections_dialog.py` | `summary_excluded_sections[style_id]` |
| `AddModelsDialog` | `add_models_dialog.py` | `extra_*_models` and the corresponding selected model |
| `GpuMemoryRecoveryDialog` | `oom_recovery_dialog.py` | `ollama_num_ctx`, `ollama_model`, `ollama_oom_policy` |
| `ExportDialog` | `main_window.py` | nothing; picks formats for one export |

The settings dialog leaves the HF token field blank when a token already exists,
and an empty field means "keep the current token" rather than "clear it".
`PdfOptionsDialog` includes a `ThemePreview` widget that paints a miniature page
in the selected palette.

Some settings are written directly by the main window rather than through a
dialog: model selections on combo change, `pdf_engine` and `summary_style` on
change, `ollama_model` and `ollama_num_ctx` on change and on close,
`recent_files` when sources are added, and window size in `closeEvent`.

## Behaviours worth knowing

**Drag and drop.** The window accepts local file URLs that pass
`is_supported_media()`, deduplicates by resolved path, appends to the timeline,
probes durations in the background, and updates the recent files list.

**Detachable tabs.** Double-clicking a tab, or using its context menu, moves it
into a floating window with a minimum size of 640 × 480. A placeholder with
"Redock" and "Show window" buttons stays behind. Closing the floating window
redocks automatically, and all tabs dock on application close. Ctrl+F routes to
whichever panel has focus, detached or not.

**Search.** Ctrl+F, F3, and Shift+F3 work in both the transcript and summary
tabs. All matches are highlighted in gold, the current match in the accent
colour.

**Speaker renaming.** Editing the Display name column fires `itemChanged`, which
is deferred by one event-loop turn with a re-entrancy guard so a rebuild
triggered by the edit does not trigger another edit. A busy overlay covers the
transcript while it re-renders. The new name is written to the transcript, the
cache, the `SpeakerNameStore`, and any existing summary Markdown, so renaming
after generating notes updates the notes too.

**Speaker table.** Selecting a row tints that speaker's blocks in the
transcript. The context menu offers filtering to one speaker and removing a
speaker along with all their segments. With a speaker selected, Home, End,
arrows, and Page Up/Down jump between that speaker's turns — suppressed while
focus is in a text field.

**Cache autoload.** When `use_cached_transcript` is on and the source set
changes, a matching cached transcript loads immediately without running the
pipeline. Start then loads from cache rather than re-transcribing.

**PDF export.** Options dialog, then a save dialog defaulting to
`{stem}_meeting.pdf`, then `PdfExportWorker`. If no summary exists yet, the
worker generates one first and streams it into the Summary tab as it goes. On
completion the user can open the file or reveal it in the file manager.

**Closing.** If transcription, summarisation, or PDF export is running, the user
is asked to confirm cancellation. All tabs dock, and window size plus Ollama and
speaker settings are saved.
