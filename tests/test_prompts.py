import pytest

from speaker_transcriber.prompts import (
    DEFAULT_STYLE,
    PROMPT_FILENAMES,
    SHARED_PROMPT_FILENAMES,
    SUMMARY_STYLES,
    get_prompt,
    get_style,
    is_known_style,
    load_prompts,
    normalize_style,
    prompts_dir,
    reload_prompts,
    style_dir,
    style_display_name,
    style_ids,
)


def test_every_style_pack_has_its_prompt_files() -> None:
    for style in SUMMARY_STYLES:
        directory = style_dir(style.style_id)
        for filename in PROMPT_FILENAMES.values():
            path = directory / filename
            assert path.is_file(), f"{style.style_id} is missing {filename}"
            assert path.read_text(encoding="utf-8").strip()


def test_shared_prompts_live_beside_the_style_folders() -> None:
    for filename in SHARED_PROMPT_FILENAMES.values():
        assert (prompts_dir() / filename).is_file()


def test_load_prompts_returns_every_pack() -> None:
    loaded = load_prompts()
    expected = set(SHARED_PROMPT_FILENAMES)
    for style in SUMMARY_STYLES:
        expected.update(f"{style.style_id}/{name}" for name in PROMPT_FILENAMES)
    assert set(loaded) == expected
    for key, text in loaded.items():
        assert text.strip()


def test_get_prompt_follows_the_style() -> None:
    load_prompts()
    meeting = get_prompt("system", "meeting_summary")
    transcript = get_prompt("system", "pure_transcription")
    assert meeting != transcript
    assert get_prompt("system") == meeting


def test_shared_continue_prompt_ignores_the_style() -> None:
    load_prompts()
    assert get_prompt("continue", "pitch_deck") == get_prompt("continue")


def test_unknown_style_falls_back_to_the_default() -> None:
    assert normalize_style("nope") == DEFAULT_STYLE
    assert not is_known_style("nope")
    assert get_style("nope").style_id == DEFAULT_STYLE
    assert get_prompt("merge", "nope") == get_prompt("merge", DEFAULT_STYLE)


def test_unknown_prompt_name_raises() -> None:
    load_prompts()
    with pytest.raises(KeyError):
        get_prompt("nonexistent", DEFAULT_STYLE)


def test_style_registry_is_consistent() -> None:
    ids = style_ids()
    assert len(ids) == len(set(ids)) == len(SUMMARY_STYLES)
    assert DEFAULT_STYLE in ids
    assert style_display_name("pitch_deck") == "Pitch Deck"


def test_reload_prompts_refreshes_cache() -> None:
    first = load_prompts()
    second = reload_prompts()
    assert first == second
