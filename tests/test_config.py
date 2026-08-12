import pytest

from speaker_transcriber.config import AppSettings, SettingsStore


def test_settings_round_trip(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    settings = AppSettings(
        model="medium",
        batch_size=2,
        language="en",
        ollama_model="llama3.2:3b",
    )
    store.save(settings)
    loaded = store.load()
    assert loaded.model == "medium"
    assert loaded.batch_size == 2
    assert loaded.language == "en"
    assert loaded.ollama_model == "llama3.2:3b"
    assert loaded.ollama_num_ctx == 8192


def test_invalid_file_falls_back_to_defaults(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    store.settings_path.write_text("{bad json", encoding="utf-8")
    assert store.load() == AppSettings()


def test_environment_token_has_priority(tmp_path, monkeypatch) -> None:
    store = SettingsStore(tmp_path)
    monkeypatch.setenv("HF_TOKEN", "environment")
    assert store.get_hf_token() == "environment"


def test_recent_files_round_trip(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    settings = AppSettings(recent_files=["C:/audio/one.wav", "C:/audio/two.mp3"])
    store.save(settings)
    loaded = store.load()
    assert loaded.recent_files == ["C:/audio/one.wav", "C:/audio/two.mp3"]


def test_invalid_recent_files_are_ignored(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    store.settings_path.write_text(
        '{"model": "medium", "recent_files": "not-a-list"}',
        encoding="utf-8",
    )
    loaded = store.load()
    assert loaded.model == "medium"
    assert loaded.recent_files == []


def test_rejects_inverted_speaker_range() -> None:
    with pytest.raises(ValueError):
        AppSettings(min_speakers=6, max_speakers=2).validate()


def test_speaker_settings_round_trip(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    settings = AppSettings(
        speaker_mode="exact",
        num_speakers=2,
        min_speakers=1,
        max_speakers=6,
    )
    store.save(settings)
    loaded = store.load()
    assert loaded.speaker_mode == "exact"
    assert loaded.num_speakers == 2
    assert loaded.min_speakers == 1
    assert loaded.max_speakers == 6


def test_legacy_exact_speaker_settings_infer_mode(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    store.settings_path.write_text(
        '{"model": "medium", "num_speakers": 3}',
        encoding="utf-8",
    )
    loaded = store.load()
    assert loaded.speaker_mode == "exact"
    assert loaded.num_speakers == 3


def test_ollama_num_ctx_round_trip(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    settings = AppSettings(ollama_num_ctx=32768)
    store.save(settings)
    assert store.load().ollama_num_ctx == 32768


def test_ollama_num_ctx_snaps_to_nearest_choice() -> None:
    settings = AppSettings(ollama_num_ctx=10000)
    settings.validate()
    assert settings.ollama_num_ctx == 8192
