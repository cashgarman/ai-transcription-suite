from speaker_transcriber.speaker_names import (
    apply_cached_speaker_names,
    apply_display_names_to_text,
    custom_speaker_names,
    is_generic_speaker_name,
    merge_cached_speaker_names,
)


def test_generic_speaker_names_are_detected() -> None:
    assert is_generic_speaker_name("SPEAKER_00")
    assert is_generic_speaker_name("Speaker 1", "SPEAKER_00")
    assert is_generic_speaker_name("SPEAKER_00", "SPEAKER_00")
    assert not is_generic_speaker_name("Cash", "SPEAKER_00")


def test_custom_speaker_names_drop_placeholders() -> None:
    assert custom_speaker_names(
        {
            "SPEAKER_00": "Cash",
            "SPEAKER_01": "Speaker 2",
            "SPEAKER_02": "SPEAKER_02",
        }
    ) == {"SPEAKER_00": "Cash"}


def test_merge_keeps_stored_names_when_current_is_generic() -> None:
    merged = merge_cached_speaker_names(
        {"SPEAKER_00": "Speaker 1", "SPEAKER_01": "Speaker 2"},
        {"SPEAKER_00": "Cash", "SPEAKER_03": "Old"},
    )
    assert merged == {"SPEAKER_00": "Cash"}


def test_merge_allows_renames_to_replace_stored_names() -> None:
    merged = merge_cached_speaker_names(
        {"SPEAKER_00": "Jordan"},
        {"SPEAKER_00": "Cash"},
    )
    assert merged == {"SPEAKER_00": "Jordan"}


def test_apply_cached_speaker_names_keeps_generic_placeholders() -> None:
    speakers = apply_cached_speaker_names(
        {"SPEAKER_00": "Speaker 1", "SPEAKER_01": "Speaker 2"},
        {"SPEAKER_00": "Cash"},
    )
    assert speakers == {"SPEAKER_00": "Cash", "SPEAKER_01": "Speaker 2"}


def test_apply_display_names_replaces_ids_and_default_labels() -> None:
    text = (
        "Participants: GranSeba, Cash, SPEAKER_00, SPEAKER_03, Speaker 1, Sergio"
    )
    updated = apply_display_names_to_text(
        text,
        {
            "SPEAKER_00": "Cash",
            "SPEAKER_01": "GranSeba",
            "SPEAKER_03": "Speaker 3",
        },
    )
    assert "SPEAKER_00" not in updated
    assert "Speaker 1" not in updated
    assert "Cash" in updated
    assert "SPEAKER_03" in updated
