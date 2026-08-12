from speaker_transcriber.prompts import (
    PROMPT_FILENAMES,
    get_prompt,
    load_prompts,
    prompts_dir,
    reload_prompts,
)


def test_prompts_dir_contains_expected_files() -> None:
    directory = prompts_dir()
    for filename in PROMPT_FILENAMES.values():
        assert (directory / filename).is_file()


def test_load_prompts_returns_non_empty_text() -> None:
    loaded = load_prompts()
    assert set(loaded) == set(PROMPT_FILENAMES)
    for name, text in loaded.items():
        assert text.strip()
        assert get_prompt(name) == text


def test_reload_prompts_refreshes_cache() -> None:
    first = load_prompts()
    second = reload_prompts()
    assert first == second
