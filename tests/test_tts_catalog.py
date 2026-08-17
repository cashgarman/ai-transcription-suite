from pathlib import Path

import pytest

from speaker_transcriber.audio.tts.factory import create_tts_backend
from speaker_transcriber.audio.tts.types import SystemVoice
from speaker_transcriber.audio.tts.voices import assign_voices
from speaker_transcriber.models.tts_catalog import (
    TtsCatalogProvider,
    WINDOWS_TTS_MODEL,
    is_piper_voice_installed,
    piper_voice_files,
)


def test_tts_catalog_lists_windows_and_piper_voices() -> None:
    provider = TtsCatalogProvider()
    names = {entry.name for entry in provider.list_models()}
    assert "en_US-lessac-medium" in names
    if provider.is_installed(WINDOWS_TTS_MODEL):
        assert WINDOWS_TTS_MODEL in names


def test_piper_voice_installed_requires_onnx_and_config(tmp_path, monkeypatch) -> None:
    from speaker_transcriber.models import tts_catalog as module

    monkeypatch.setattr(module, "tts_models_dir", lambda: tmp_path)
    voice_id = "en_US-lessac-medium"
    assert not is_piper_voice_installed(voice_id)
    onnx_path, config_path = piper_voice_files(voice_id)
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    onnx_path.write_bytes(b"onnx")
    assert not is_piper_voice_installed(voice_id)
    config_path.write_text("{}")
    assert is_piper_voice_installed(voice_id)


def test_assign_voices_prefers_selected_piper_voice() -> None:
    voices = [
        SystemVoice("en_US-lessac-medium", "Lessac", "male"),
        SystemVoice("en_US-amy-medium", "Amy", "female"),
    ]
    mapping = assign_voices(
        ["SPEAKER_00", "SPEAKER_01"],
        voices,
        genders={"SPEAKER_00": "female", "SPEAKER_01": "male"},
        preferred_voice="en_US-lessac-medium",
    )
    assert mapping["SPEAKER_01"].id == "en_US-lessac-medium"
    assert mapping["SPEAKER_00"].id == "en_US-amy-medium"


def test_create_tts_backend_accepts_windows_on_win32() -> None:
    backend = create_tts_backend(WINDOWS_TTS_MODEL)
    close = getattr(backend, "close", None)
    if callable(close):
        close()


def test_create_tts_backend_builds_piper_backend_for_catalog_voice() -> None:
    from speaker_transcriber.audio.tts.piper_backend import PiperTtsBackend

    backend = create_tts_backend("en_US-lessac-medium")
    assert isinstance(backend, PiperTtsBackend)
    backend.close()


def test_download_piper_voice_uses_shared_hub_cache(tmp_path, monkeypatch) -> None:
    from threading import Event

    from speaker_transcriber.models import tts_catalog as module

    voices_dir = tmp_path / "voices"
    hub_cache = tmp_path / "hf_cache"
    monkeypatch.setattr(module, "tts_models_dir", lambda: voices_dir)
    monkeypatch.setattr(module, "piper_hub_cache_dir", lambda: hub_cache)
    monkeypatch.setattr(
        "speaker_transcriber.huggingface_setup.configure_huggingface_client",
        lambda: None,
    )

    recorded: list[dict[str, object | None]] = []

    def fake_hf_hub_download(
        *,
        repo_id: str,
        filename: str,
        cache_dir=None,
        local_dir=None,
        tqdm_class=None,
    ):
        recorded.append(
            {"repo_id": repo_id, "filename": filename, "cache_dir": cache_dir, "local_dir": local_dir}
        )
        cached = Path(cache_dir) / Path(filename).name
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(b"voice-bytes")
        return str(cached)

    monkeypatch.setattr("huggingface_hub.hf_hub_download", fake_hf_hub_download)

    module._download_piper_voice("en_US-lessac-medium", None, Event())

    onnx_path, config_path = module.piper_voice_files("en_US-lessac-medium")
    assert onnx_path.read_bytes() == b"voice-bytes"
    assert config_path.read_bytes() == b"voice-bytes"
    assert len(recorded) == 2
    assert all(call["local_dir"] is None for call in recorded)
    assert all(call["cache_dir"] == hub_cache for call in recorded)
    assert not any(voices_dir.rglob(".cache"))
