from __future__ import annotations

import logging
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from speaker_transcriber.config import app_data_dir
from speaker_transcriber.models.hf_catalog import bind_progress_tqdm
from speaker_transcriber.models.model_catalog import (
    CatalogEntry,
    DownloadProgress,
    disk_usage_for,
    format_bytes,
)


LOGGER = logging.getLogger("speaker_transcriber.tts_catalog")

PIPER_VOICES_REPO = "rhasspy/piper-voices"
WINDOWS_TTS_MODEL = "windows"
DEFAULT_TTS_MODEL = WINDOWS_TTS_MODEL if sys.platform == "win32" else "en_US-lessac-medium"


@dataclass(frozen=True)
class PiperVoiceSpec:
    voice_id: str
    display_name: str
    gender: str
    language: str
    repo_path: str
    size_bytes: int | None = None
    description: str = ""


PIPER_VOICE_CATALOG: tuple[PiperVoiceSpec, ...] = (
    PiperVoiceSpec(
        "en_US-lessac-medium",
        "Lessac (US English)",
        "male",
        "en",
        "en/en_US/lessac/medium",
        63_000_000,
        "Clear US male narrator",
    ),
    PiperVoiceSpec(
        "en_US-amy-medium",
        "Amy (US English)",
        "female",
        "en",
        "en/en_US/amy/medium",
        63_000_000,
        "Natural US female voice",
    ),
    PiperVoiceSpec(
        "en_US-ryan-medium",
        "Ryan (US English)",
        "male",
        "en",
        "en/en_US/ryan/medium",
        63_000_000,
        "Conversational US male voice",
    ),
    PiperVoiceSpec(
        "en_US-kristin-medium",
        "Kristin (US English)",
        "female",
        "en",
        "en/en_US/kristin/medium",
        63_000_000,
        "Bright US female voice",
    ),
    PiperVoiceSpec(
        "en_GB-alan-medium",
        "Alan (British English)",
        "male",
        "en",
        "en/en_GB/alan/medium",
        63_000_000,
        "British male narrator",
    ),
    PiperVoiceSpec(
        "en_GB-jenny_dioco-medium",
        "Jenny Dioco (British English)",
        "female",
        "en",
        "en/en_GB/jenny_dioco/medium",
        63_000_000,
        "British female voice",
    ),
)

_CATALOG_BY_ID = {spec.voice_id: spec for spec in PIPER_VOICE_CATALOG}


def tts_models_dir() -> Path:
    return app_data_dir() / "tts_models" / "piper"


def piper_hub_cache_dir() -> Path:
    """Shared Hugging Face cache for Piper voices (avoids per-voice .cache trees)."""
    return app_data_dir() / "hf_cache"


def piper_voice_spec(voice_id: str) -> PiperVoiceSpec | None:
    return _CATALOG_BY_ID.get(voice_id)


def is_piper_voice_id(model_id: str) -> bool:
    return model_id != WINDOWS_TTS_MODEL and model_id in _CATALOG_BY_ID


def piper_voice_files(voice_id: str) -> tuple[Path, Path]:
    directory = tts_models_dir() / voice_id
    return (
        directory / f"{voice_id}.onnx",
        directory / f"{voice_id}.onnx.json",
    )


def is_piper_voice_installed(voice_id: str) -> bool:
    onnx_path, config_path = piper_voice_files(voice_id)
    return onnx_path.is_file() and config_path.is_file() and onnx_path.stat().st_size > 0


def list_installed_piper_voice_ids(extra: list[str] | None = None) -> list[str]:
    installed: list[str] = []
    seen: set[str] = set()
    for spec in PIPER_VOICE_CATALOG:
        if is_piper_voice_installed(spec.voice_id):
            installed.append(spec.voice_id)
            seen.add(spec.voice_id)
    for voice_id in extra or ():
        if voice_id in seen or voice_id == WINDOWS_TTS_MODEL:
            continue
        if is_piper_voice_installed(voice_id):
            installed.append(voice_id)
            seen.add(voice_id)
    return installed


def _download_piper_voice(
    voice_id: str,
    on_progress: Callable[[DownloadProgress], None] | None,
    cancel_event: Event,
) -> None:
    spec = piper_voice_spec(voice_id)
    if spec is None:
        raise RuntimeError(f"Unknown Piper voice: {voice_id}")
    from huggingface_hub import hf_hub_download

    from speaker_transcriber.huggingface_setup import (
        configure_huggingface_client,
        retry_hub_operation,
    )

    configure_huggingface_client()
    destination = tts_models_dir() / voice_id
    destination.mkdir(parents=True, exist_ok=True)
    cache_dir = piper_hub_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    tqdm_class = bind_progress_tqdm(on_progress, cancel_event)
    for filename in (f"{voice_id}.onnx", f"{voice_id}.onnx.json"):
        if cancel_event.is_set():
            raise InterruptedError("Download cancelled.")
        remote = f"{spec.repo_path}/{filename}"
        downloaded = retry_hub_operation(
            lambda remote=remote: hf_hub_download(
                repo_id=PIPER_VOICES_REPO,
                filename=remote,
                cache_dir=cache_dir,
                tqdm_class=tqdm_class,
            ),
            cancel_event=cancel_event,
            what=f"download {voice_id} ({filename})",
        )
        source = Path(downloaded)
        target = destination / filename
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)


class TtsCatalogProvider:
    id = "tts"
    title = "Text-to-speech voices"

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def list_models(self, query: str = "") -> list[CatalogEntry]:
        needle = query.strip().lower()
        entries: list[CatalogEntry] = []
        if sys.platform == "win32" and (
            not needle or "windows" in needle or "built" in needle or "sapi" in needle
        ):
            entries.append(
                CatalogEntry(
                    name=WINDOWS_TTS_MODEL,
                    display_name="Windows voices (built-in)",
                    installed=True,
                    description="Installed Microsoft SAPI voices",
                    family="windows",
                    role="Built-in",
                )
            )
        for spec in PIPER_VOICE_CATALOG:
            haystack = f"{spec.voice_id} {spec.display_name} {spec.description}".lower()
            if needle and needle not in haystack:
                continue
            entries.append(self._entry_for(spec))
        if needle and not entries and is_piper_voice_id(query.strip()):
            spec = piper_voice_spec(query.strip())
            if spec is not None:
                entries.append(self._entry_for(spec))
        return entries

    def list_variants(self, family: str) -> list[CatalogEntry]:
        return []

    def is_installed(self, name: str) -> bool:
        if name == WINDOWS_TTS_MODEL:
            return sys.platform == "win32"
        return is_piper_voice_installed(name)

    def download(
        self,
        name: str,
        on_progress: Callable[[DownloadProgress], None] | None,
        cancel_event: Event,
    ) -> None:
        if name == WINDOWS_TTS_MODEL:
            return
        _download_piper_voice(name, on_progress, cancel_event)

    def cache_path(self) -> Path:
        return tts_models_dir()

    def disk_usage(self):
        return disk_usage_for(self.cache_path())

    def entry_for(self, voice_id: str) -> CatalogEntry:
        if voice_id == WINDOWS_TTS_MODEL:
            return CatalogEntry(
                name=WINDOWS_TTS_MODEL,
                display_name="Windows voices (built-in)",
                installed=sys.platform == "win32",
                description="Installed Microsoft SAPI voices",
                family="windows",
                role="Built-in",
            )
        spec = piper_voice_spec(voice_id)
        if spec is None:
            return CatalogEntry(
                name=voice_id,
                display_name=voice_id,
                installed=is_piper_voice_installed(voice_id),
                family="piper",
            )
        return self._entry_for(spec)

    def _entry_for(self, spec: PiperVoiceSpec) -> CatalogEntry:
        size_label = format_bytes(spec.size_bytes) if spec.size_bytes else "—"
        return CatalogEntry(
            name=spec.voice_id,
            display_name=spec.display_name,
            size_bytes=spec.size_bytes,
            installed=is_piper_voice_installed(spec.voice_id),
            description=spec.description or f"{spec.language.upper()} · {spec.gender}",
            family="piper",
            role=f"{spec.gender.title()} · {size_label}",
        )
