"""Prompt Lab preferences, kept separate from the application's settings.

The lab has its own model choices — a generator, a summarizer under test, a
judge, and an optimizer — and none of them should disturb what the main window
is configured to use.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from speaker_transcriber.config import DEFAULT_OLLAMA_NUM_CTX, snap_ollama_num_ctx
from speaker_transcriber.prompts import DEFAULT_STYLE, normalize_style
from speaker_transcriber.promptlab.scenarios import DEFAULT_KIND, kind_ids
from speaker_transcriber.promptlab.types import (
    DISFLUENCY_LEVELS,
    GENERATION_MODES,
    GROUNDED_MODE,
)


@dataclass
class LabSettings:
    generator_model: str = ""
    generator_num_ctx: int = DEFAULT_OLLAMA_NUM_CTX
    generator_temperature: float = 0.85
    summarizer_model: str = ""
    summarizer_num_ctx: int = DEFAULT_OLLAMA_NUM_CTX
    judge_model: str = ""
    judge_num_ctx: int = DEFAULT_OLLAMA_NUM_CTX
    optimizer_model: str = ""
    optimizer_num_ctx: int = DEFAULT_OLLAMA_NUM_CTX
    style_id: str = DEFAULT_STYLE
    meeting_kind: str = DEFAULT_KIND
    generation_mode: str = GROUNDED_MODE
    disfluency: str = "light"
    duration_minutes: int = 30
    batch_size: int = 4
    base_seed: int = 1
    random_kind: bool = True
    window_width: int = 1360
    window_height: int = 900
    last_variant_a: str = ""
    last_variant_b: str = ""

    def validate(self) -> None:
        self.style_id = normalize_style(self.style_id)
        if self.meeting_kind not in kind_ids():
            self.meeting_kind = DEFAULT_KIND
        if self.generation_mode not in GENERATION_MODES:
            self.generation_mode = GROUNDED_MODE
        if self.disfluency not in DISFLUENCY_LEVELS:
            self.disfluency = "light"
        self.duration_minutes = max(5, min(180, int(self.duration_minutes)))
        self.batch_size = max(1, min(64, int(self.batch_size)))
        self.base_seed = max(0, int(self.base_seed))
        self.generator_temperature = max(0.0, min(2.0, float(self.generator_temperature)))
        for name in (
            "generator_num_ctx",
            "summarizer_num_ctx",
            "judge_num_ctx",
            "optimizer_num_ctx",
        ):
            setattr(self, name, snap_ollama_num_ctx(getattr(self, name)))
        self.window_width = max(900, int(self.window_width))
        self.window_height = max(600, int(self.window_height))

    def with_model_fallback(self, model_name: str) -> LabSettings:
        """Fill any unset model role with the app's configured Ollama model."""
        for name in (
            "generator_model",
            "summarizer_model",
            "judge_model",
            "optimizer_model",
        ):
            if not str(getattr(self, name) or "").strip():
                setattr(self, name, model_name)
        return self


class LabSettingsStore:
    def __init__(self, root: Path) -> None:
        self.path = Path(root) / "settings.json"

    def load(self) -> LabSettings:
        if not self.path.is_file():
            return LabSettings()
        try:
            data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return LabSettings()
        known = {item.name for item in fields(LabSettings)}
        settings = LabSettings(
            **{key: value for key, value in data.items() if key in known}
        )
        settings.validate()
        return settings

    def save(self, settings: LabSettings) -> None:
        settings.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(settings), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
