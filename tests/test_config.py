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


def test_rejects_conflicting_speaker_counts() -> None:
    with pytest.raises(ValueError):
        AppSettings(num_speakers=2, min_speakers=1).validate()
