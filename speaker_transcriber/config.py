from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from speaker_transcriber.huggingface_setup import load_project_env


SUPPORTED_MODELS = ("medium", "distil-large-v3", "large-v3")
SUPPORTED_COMPUTE_TYPES = ("int8_float16", "float16", "int8", "float32")
SUPPORTED_DEVICES = ("cuda", "cpu")


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
    merge_gap_seconds: float = 0.5
    max_block_duration_seconds: float = 30.0
    inherit_speaker_threshold_seconds: float = 0.3
    alignment_device: str = "cuda"
    diarization_device: str = "cuda"
    window_width: int = 1200
    window_height: int = 820
    use_cached_transcript: bool = True
    ollama_model: str = "qwen3.5:9b"

    def validate(self) -> None:
        if self.model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported model: {self.model}")
        if self.compute_type not in SUPPORTED_COMPUTE_TYPES:
            raise ValueError(f"Unsupported compute type: {self.compute_type}")
        if self.batch_size < 1:
            raise ValueError("Batch size must be at least 1.")
        if self.alignment_device not in SUPPORTED_DEVICES:
            raise ValueError("Alignment device must be 'cuda' or 'cpu'.")
        if self.diarization_device not in SUPPORTED_DEVICES:
            raise ValueError("Diarization device must be 'cuda' or 'cpu'.")
        if self.num_speakers is not None and (
            self.min_speakers is not None or self.max_speakers is not None
        ):
            raise ValueError("Exact speaker count cannot be combined with min/max counts.")
        if (
            self.min_speakers is not None
            and self.max_speakers is not None
            and self.min_speakers > self.max_speakers
        ):
            raise ValueError("Minimum speakers cannot exceed maximum speakers.")
        if self.merge_gap_seconds < 0 or self.max_block_duration_seconds <= 0:
            raise ValueError("Transcript merge thresholds must be positive.")


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
            settings = AppSettings(**{key: value for key, value in data.items() if key in allowed})
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
