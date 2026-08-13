from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from speaker_transcriber.huggingface_setup import load_project_env


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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def snap_ollama_num_ctx(value: int) -> int:
    return min(OLLAMA_CTX_CHOICES, key=lambda choice: abs(choice - int(value)))


def previous_ollama_num_ctx(value: int) -> int | None:
    """The next smaller context choice, or None when already at the smallest."""
    current = snap_ollama_num_ctx(value)
    smaller = [choice for choice in OLLAMA_CTX_CHOICES if choice < current]
    return smaller[-1] if smaller else None


def format_ctx_label(num_ctx: int) -> str:
    if num_ctx >= 1024 and num_ctx % 1024 == 0:
        return f"{num_ctx // 1024}k"
    return str(num_ctx)


def infer_speaker_mode(
    speaker_mode: str | None,
    num_speakers: int | None,
    min_speakers: int | None,
    max_speakers: int | None,
) -> str:
    if speaker_mode in SPEAKER_MODES:
        return speaker_mode
    if num_speakers is not None:
        return "exact"
    if min_speakers is not None or max_speakers is not None:
        return "minmax"
    return "automatic"


def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / "SpeakerTranscriber"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "speaker_transcriber"


@dataclass
class AppSettings:
    model: str = "distil-large-v3"
    compute_type: str = "int8_float16"
    batch_size: int = 4
    language: str = "auto"
    output_directory: str = ""
    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    speaker_mode: str = "automatic"
    merge_gap_seconds: float = 0.5
    max_block_duration_seconds: float = 30.0
    inherit_speaker_threshold_seconds: float = 0.3
    alignment_device: str = "cuda"
    diarization_device: str = "cuda"
    alignment_model: str = DEFAULT_ALIGNMENT_MODEL
    diarization_model: str = DEFAULT_DIARIZATION_MODEL
    extra_whisper_models: list[str] = field(default_factory=list)
    extra_alignment_models: list[str] = field(default_factory=list)
    extra_diarization_models: list[str] = field(default_factory=list)
    pdf_engine: str = "reportlab"
    window_width: int = 1200
    window_height: int = 820
    use_cached_transcript: bool = True
    ollama_model: str = "qwen3.5:9b"
    ollama_num_ctx: int = DEFAULT_OLLAMA_NUM_CTX
    ollama_oom_policy: str = ""
    recent_files: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not str(self.model or "").strip():
            raise ValueError("Transcription model is required.")
        if self.compute_type not in SUPPORTED_COMPUTE_TYPES:
            raise ValueError(f"Unsupported compute type: {self.compute_type}")
        if self.batch_size < 1:
            raise ValueError("Batch size must be at least 1.")
        if self.alignment_device not in SUPPORTED_DEVICES:
            raise ValueError("Alignment device must be 'cuda' or 'cpu'.")
        if self.diarization_device not in SUPPORTED_DEVICES:
            raise ValueError("Diarization device must be 'cuda' or 'cpu'.")
        if self.speaker_mode not in SPEAKER_MODES:
            self.speaker_mode = infer_speaker_mode(
                None,
                self.num_speakers,
                self.min_speakers,
                self.max_speakers,
            )
        if (
            self.min_speakers is not None
            and self.max_speakers is not None
            and self.min_speakers > self.max_speakers
        ):
            raise ValueError("Minimum speakers cannot exceed maximum speakers.")
        if self.merge_gap_seconds < 0 or self.max_block_duration_seconds <= 0:
            raise ValueError("Transcript merge thresholds must be positive.")
        try:
            ctx = int(self.ollama_num_ctx)
        except (TypeError, ValueError) as exc:
            raise ValueError("Ollama context length must be an integer.") from exc
        if ctx not in OLLAMA_CTX_CHOICES:
            self.ollama_num_ctx = snap_ollama_num_ctx(ctx)
        else:
            self.ollama_num_ctx = ctx
        policy = str(self.ollama_oom_policy or "").strip()
        self.ollama_oom_policy = policy if policy in OLLAMA_OOM_POLICIES else ""
        engine = str(self.pdf_engine or "reportlab").strip().lower()
        self.pdf_engine = engine if engine in PDF_ENGINES else "reportlab"
        self.alignment_model = str(self.alignment_model or DEFAULT_ALIGNMENT_MODEL).strip() or DEFAULT_ALIGNMENT_MODEL
        self.diarization_model = (
            str(self.diarization_model or DEFAULT_DIARIZATION_MODEL).strip()
            or DEFAULT_DIARIZATION_MODEL
        )
        self.extra_whisper_models = _string_list(self.extra_whisper_models)
        self.extra_alignment_models = _string_list(self.extra_alignment_models)
        self.extra_diarization_models = _string_list(self.extra_diarization_models)


class SettingsStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or app_data_dir()
        self.settings_path = self.directory / "settings.json"

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            return AppSettings()
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            allowed = {item.name for item in fields(AppSettings)}
            filtered = {key: value for key, value in data.items() if key in allowed}
            if "recent_files" in filtered and not isinstance(
                filtered["recent_files"], list
            ):
                filtered["recent_files"] = []
            elif "recent_files" in filtered:
                filtered["recent_files"] = [
                    str(item)
                    for item in filtered["recent_files"]
                    if isinstance(item, str) and item.strip()
                ]
            if "ollama_num_ctx" in filtered:
                try:
                    filtered["ollama_num_ctx"] = int(filtered["ollama_num_ctx"])
                except (TypeError, ValueError):
                    filtered.pop("ollama_num_ctx")
            for list_key in (
                "extra_whisper_models",
                "extra_alignment_models",
                "extra_diarization_models",
            ):
                if list_key in filtered:
                    filtered[list_key] = _string_list(filtered[list_key])
            if "speaker_mode" not in filtered or filtered.get("speaker_mode") not in SPEAKER_MODES:
                filtered["speaker_mode"] = infer_speaker_mode(
                    None,
                    filtered.get("num_speakers"),
                    filtered.get("min_speakers"),
                    filtered.get("max_speakers"),
                )
            settings = AppSettings(**filtered)
            settings.validate()
            return settings
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        settings.validate()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(asdict(settings), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_hf_token(self, explicit: str | None = None) -> str | None:
        if explicit:
            return explicit.strip() or None
        load_project_env()
        environment_token = os.environ.get("HF_TOKEN", "").strip()
        if environment_token:
            return environment_token
        try:
            import keyring

            token = (keyring.get_password("SpeakerTranscriber", "HF_TOKEN") or "").strip()
            return token or None
        except Exception:
            return None

    def save_hf_token(self, token: str) -> None:
        try:
            import keyring

            keyring.set_password("SpeakerTranscriber", "HF_TOKEN", token.strip())
        except Exception as exc:
            raise RuntimeError(
                "The operating-system credential store is unavailable. "
                "Set HF_TOKEN in the environment or .env file instead."
            ) from exc
