# Configuration and runtime data

Everything the application persists, where it puts it, and how secrets are
handled.

## Where things live

| Data | Windows | Linux |
|---|---|---|
| Settings | `%APPDATA%\SpeakerTranscriber\settings.json` | `~/.config/speaker_transcriber/settings.json` |
| Transcript cache | `…\SpeakerTranscriber\transcripts\` | `~/.config/speaker_transcriber/transcripts/` |
| Logs | `…\SpeakerTranscriber\logs\speaker_transcriber.log` | `~/.config/speaker_transcriber/logs/…` |
| HF token | OS credential store | OS credential store (via `keyring`) |

The root is `app_data_dir()` in `speaker_transcriber/config.py`:

```93:97:speaker_transcriber/config.py
def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / "SpeakerTranscriber"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "speaker_transcriber"
```

Model weights are not stored here. They go to the normal Hugging Face cache
(`HF_HOME`, `HF_HUB_CACHE`) and the normal Ollama models directory
(`OLLAMA_MODELS`, default `~/.ollama/models`), so they are shared with any other
tool on the machine and are not duplicated per application.

## Settings schema

`AppSettings` is a dataclass; the JSON file is `asdict()` of it. Every field:

### Transcription

| Key | Type | Default |
|---|---|---|
| `model` | str | `"distil-large-v3"` |
| `compute_type` | str | `"int8_float16"` |
| `batch_size` | int | `4` |
| `language` | str | `"auto"` |
| `alignment_device` | str | `"cuda"` |
| `diarization_device` | str | `"cuda"` |
| `alignment_model` | str | `"auto"` |
| `diarization_model` | str | `"pyannote/speaker-diarization-3.1"` |

### Speakers and merging

| Key | Type | Default |
|---|---|---|
| `speaker_mode` | str | `"automatic"` — also `"exact"`, `"minmax"` |
| `num_speakers` | int \| None | `None` |
| `min_speakers` | int \| None | `None` |
| `max_speakers` | int \| None | `None` |
| `merge_gap_seconds` | float | `0.5` |
| `max_block_duration_seconds` | float | `30.0` |
| `inherit_speaker_threshold_seconds` | float | `0.3` |

### Notes and export

| Key | Type | Default |
|---|---|---|
| `ollama_model` | str | `"qwen3.5:9b"` |
| `ollama_num_ctx` | int | `8192` |
| `ollama_oom_policy` | str | `""` — also `"reduce_ctx"`, `"smaller_model"` |
| `summary_style` | str | `"meeting_summary"` |
| `summary_excluded_sections` | dict[str, list[str]] | `{}` |
| `pdf_engine` | str | `"reportlab"` |
| `pdf_theme` | str | `"light"` |
| `pdf_options` | dict[str, bool] | `{}` |
| `output_directory` | str | `""` |

### Application state

| Key | Type | Default |
|---|---|---|
| `extra_whisper_models` | list[str] | `[]` |
| `extra_alignment_models` | list[str] | `[]` |
| `extra_diarization_models` | list[str] | `[]` |
| `recent_files` | list[str] | `[]` |
| `window_width` | int | `1200` |
| `window_height` | int | `820` |
| `use_cached_transcript` | bool | `True` |

Two fields store only deviations from defaults rather than complete state.
`pdf_options` holds the toggles that differ from their registered defaults, and
`summary_excluded_sections` holds only the sections a user switched off. This
means adding a new PDF option or a new summary section does not require a
settings migration — absent keys pick up the new default automatically.

## Loading and validation

`SettingsStore.load()` is written so that a corrupt or hand-edited settings file
can never prevent startup. It filters unknown keys, coerces the types it knows
can go wrong, constructs `AppSettings`, and calls `validate()`. Any `OSError`,
`ValueError`, `TypeError`, or `JSONDecodeError` anywhere in that path returns
fresh defaults instead of propagating.

`validate()` runs on both load and save and is a mix of hard failures and quiet
repairs. It raises on things that would produce a wrong result — an empty model
name, an unsupported compute type, a batch size below 1, a bad device, minimum
speakers above maximum, negative merge thresholds. It repairs things where a
sensible value exists: an unknown `pdf_engine` becomes `reportlab`, an unknown
`pdf_theme` goes through `normalize_theme()`, an unknown `summary_style` goes
through `normalize_style()`, an off-grid `ollama_num_ctx` snaps to the nearest
allowed choice, and an unrecognised OOM policy is cleared.

There is one migration. `speaker_mode` was added after the three speaker-count
fields, so when it is missing or invalid, `infer_speaker_mode()` derives it:
`num_speakers` set means `"exact"`, a min or max set means `"minmax"`, otherwise
`"automatic"`.

Validated choice lists:

```18:28:speaker_transcriber/config.py
RECOMMENDED_WHISPER_MODELS = ("large-v3", "distil-large-v3", "medium")
SUPPORTED_MODELS = RECOMMENDED_WHISPER_MODELS
SUPPORTED_COMPUTE_TYPES = ("int8_float16", "float16", "int8", "float32")
SUPPORTED_DEVICES = ("cuda", "cpu")
SPEAKER_MODES = ("automatic", "exact", "minmax")
PDF_ENGINES = ("reportlab", "weasyprint")
OLLAMA_CTX_CHOICES = (4096, 8192, 16384, 32768, 65536, 131072)
DEFAULT_OLLAMA_NUM_CTX = 8192
OLLAMA_OOM_POLICIES = ("", "reduce_ctx", "smaller_model")
DEFAULT_ALIGNMENT_MODEL = "auto"
DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
```

## The Hugging Face token

The token is needed only for pyannote diarization. It is never written to
`settings.json`.

`SettingsStore.get_hf_token()` resolves in this order:

1. An explicitly passed value, such as the CLI's `--hf-token`.
2. `HF_TOKEN` from the environment, after `load_project_env()` has loaded `.env`
   from the working directory and the project root.
3. The OS credential store, under service `SpeakerTranscriber` and username
   `HF_TOKEN`.

`save_hf_token()` writes to the same keyring entry. If the credential store is
unavailable — common on headless Linux without a keyring daemon — it raises a
`RuntimeError` telling the user to use `HF_TOKEN` or `.env` instead, rather than
silently failing to save.

Every log handler carries `SecretRedactionFilter`, which rewrites three patterns
case-insensitively before a record is emitted:

| Pattern | Replacement |
|---|---|
| `(HF_TOKEN\s*[=:]\s*)\S+` | `\1[REDACTED]` |
| `(--hf-token(?:=\|\s+))\S+` | `\1[REDACTED]` |
| `(Bearer\s+)[A-Za-z0-9_.-]+` | `\1[REDACTED]` |

## Environment variables

| Variable | Read by | Purpose |
|---|---|---|
| `HF_TOKEN` | `config.py` | Hugging Face read token |
| `HF_HUB_INSECURE_SSL` | `huggingface_setup.py` | Set to `1` to skip TLS verification for Hugging Face downloads. A workaround for corporate TLS interception; logged as a warning |
| `HF_HOME`, `HF_HUB_CACHE`, `HUGGINGFACE_HUB_CACHE` | `model_catalog.py` | Locate the model cache to report what is installed |
| `OLLAMA_MODELS` | `model_catalog.py` | Ollama model directory |
| `APPDATA`, `XDG_CONFIG_HOME` | `config.py` | Application data root |
| `WEASYPRINT_DLL_DIRECTORIES` | `weasyprint_exporter.py` | GTK/Pango DLL directories on Windows; also written by the app when it discovers them |
| `PATH` | `cuda_setup.py` | Prepended with NVIDIA cuDNN, cuBLAS, and NVRTC bin directories on Windows |
| `QT_QPA_PLATFORM` | `tests/conftest.py` | Set to `offscreen` so widget tests run headless |

## Transcript cache

`speaker_transcriber/cache/transcript_cache.py` stores completed transcripts so
reopening a file is instant.

| File | Contents |
|---|---|
| `{key}.json` | The full `TranscriptResult`, via the JSON exporter's round trip |
| `{key}.speakers.json` | Custom speaker display names |
| `{key}.summary.{style_id}.md` | Generated notes, one file per style |
| `{key}.summary.md` | Legacy path, still read for the default style |

The key comes from `MediaSource.cache_key()`. For a single file it is the
filename stem with no content hash, so the cache hits whenever the same filename
is opened. This is right for the common case and wrong if a file is replaced
in place; the user can re-transcribe to refresh it, or turn off
`use_cached_transcript`.

All writes go through a `NamedTemporaryFile` and `os.replace()`, so an
interrupted write cannot leave a truncated cache file.

Summaries are cached per style, so switching between Meeting Summary and Pitch
Deck does not discard either. Saving a default-style summary removes the legacy
`.summary.md`; saving empty text deletes the summary files.

There is no size limit, no LRU, and no expiry. Deletion is explicit, via
`TranscriptCache.delete()`, which removes the transcript, the speaker sidecar,
and every summary file for that key.

## Speaker names

Names persist separately from transcripts so that renaming survives a
re-transcription. `SpeakerNameStore` writes `{key}.speakers.json` in the same
directory as the transcript cache.

`speaker_names.py` distinguishes custom names from generated ones. A name is
generic — and therefore not worth persisting — when it matches `SPEAKER_\d+`,
matches `Speaker\s+\d+`, equals its own label, or is blank. Only custom names
are stored, so the file stays empty until someone actually renames a speaker.

`merge_cached_speaker_names()` resolves conflicts: an incoming custom name wins,
a stored custom name is kept when the current value is generic, and labels not
present in the current transcript are dropped.

A legacy store at `{app_data_dir}/speaker_names/sessions.json` is still read for
migration, including keys prefixed with the primary file's stem.

## Logging

Application logs go to `{app_data_dir}/logs/speaker_transcriber.log` through a
`RotatingFileHandler` with a 5 MiB limit and 3 backups, UTF-8. The file
formatter writes JSON lines with `timestamp`, `level`, `logger`, `message`, and
`exception` when present — structured so a support log can be filtered rather
than read linearly.

Three handlers attach to the `speaker_transcriber` logger: the rotating file, a
stream handler, and (in the GUI) a `QueueHandler` feeding the log panel. All
three carry the redaction filter. The level is `INFO`, or `DEBUG` with
`--verbose`.

`log_system_information()` records the application version, Python and platform
versions, PyTorch version, CUDA availability, GPU name and VRAM, and the process
ID at startup. Most support questions are answerable from those lines alone.

`debug_log.py` is separate and is a development aid, not part of the product
logging. It appends NDJSON to `debug-4ba2aa.log` at the project root, has no
rotation, and swallows its own failures. It is **not** redacted, so treat that
file as potentially sensitive.

## Platform metrics

`gpu_stats.py` prefers shelling out to `nvidia-smi` with a 1.5 second timeout:

```
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits
```

It falls back to `torch.cuda.mem_get_info()`, which gives memory but not
utilisation. NVML is not used, which avoids a dependency and a class of driver
version mismatches.

`host_stats.py` reads CPU and RAM without psutil: `GlobalMemoryStatusEx` and
`GetSystemTimes` on Windows, `/proc/meminfo` and `/proc/stat` on POSIX. CPU
percentage needs two samples, so the first call returns `None` and the meter
stays blank for one tick.

The main window polls both every second.

## Network activity and privacy

| Destination | When | What |
|---|---|---|
| `huggingface.co` | Model download and catalog browsing | Model metadata and weights |
| `ollama.com` | Model catalog browsing | Search results and library tag pages |
| Local Ollama daemon | Notes generation | Prompts and transcript text, over loopback |

Audio, transcripts, and generated notes never leave the machine. Transcription,
alignment, and diarization make no network calls once models are cached; the
prompts sent to Ollama go to a local process, not a remote API.

There is no telemetry and no analytics.
