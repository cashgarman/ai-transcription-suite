import pytest

from speaker_transcriber.config import (
    AppSettings,
    SettingsStore,
    previous_ollama_num_ctx,
)


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


def test_ollama_oom_policy_round_trip(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    store.save(AppSettings(ollama_oom_policy="reduce_ctx"))
    assert store.load().ollama_oom_policy == "reduce_ctx"


def test_unknown_ollama_oom_policy_is_cleared() -> None:
    settings = AppSettings(ollama_oom_policy="explode")
    settings.validate()
    assert settings.ollama_oom_policy == ""


def test_previous_ollama_num_ctx_steps_down_one_choice() -> None:
    assert previous_ollama_num_ctx(16384) == 8192
    assert previous_ollama_num_ctx(8192) == 4096
    assert previous_ollama_num_ctx(4096) is None
    assert previous_ollama_num_ctx(10000) == 4096


def test_pipeline_model_settings_round_trip(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    settings = AppSettings(
        model="tiny",
        alignment_model="jonatasgrosman/wav2vec2-large-xlsr-53-english",
        diarization_model="pyannote/speaker-diarization-3.0",
        extra_whisper_models=["tiny", "base"],
        extra_alignment_models=["facebook/wav2vec2-base-960h"],
        extra_diarization_models=["pyannote/speaker-diarization-3.0"],
        pdf_engine="weasyprint",
    )
    store.save(settings)
    loaded = store.load()
    assert loaded.model == "tiny"
    assert loaded.alignment_model == "jonatasgrosman/wav2vec2-large-xlsr-53-english"
    assert loaded.diarization_model == "pyannote/speaker-diarization-3.0"
    assert loaded.extra_whisper_models == ["tiny", "base"]
    assert loaded.extra_alignment_models == ["facebook/wav2vec2-base-960h"]
    assert loaded.pdf_engine == "weasyprint"


def test_unknown_whisper_model_is_allowed() -> None:
    settings = AppSettings(model="Systran/faster-whisper-tiny")
    settings.validate()
    assert settings.model == "Systran/faster-whisper-tiny"


def test_invalid_pdf_engine_falls_back_to_reportlab() -> None:
    settings = AppSettings(pdf_engine="not-an-engine")
    settings.validate()
    assert settings.pdf_engine == "reportlab"


def test_invalid_pdf_theme_falls_back_to_light() -> None:
    settings = AppSettings(pdf_theme="neon")
    settings.validate()
    assert settings.pdf_theme == "light"


def test_pdf_theme_round_trip(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    store.save(AppSettings(pdf_theme="dark"))
    assert store.load().pdf_theme == "dark"


def test_summary_style_defaults_to_meeting_summary() -> None:
    settings = AppSettings()
    settings.validate()
    assert settings.summary_style == "meeting_summary"


def test_invalid_summary_style_falls_back_to_meeting_summary() -> None:
    settings = AppSettings(summary_style="not-a-style")
    settings.validate()
    assert settings.summary_style == "meeting_summary"


def test_summary_style_round_trip(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    store.save(AppSettings(summary_style="pitch_deck"))
    assert store.load().summary_style == "pitch_deck"
