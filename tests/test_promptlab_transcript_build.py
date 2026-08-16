from speaker_transcriber.export.text_exporter import render_summary_source
from speaker_transcriber.promptlab.scenarios import build_scenario
from speaker_transcriber.promptlab.transcript_build import (
    build_transcript_result,
    parse_dialogue,
    result_from_payload,
    result_to_payload,
    transcript_word_count,
)


def _scenario():
    return build_scenario(1234, kind_id="product_review", duration_minutes=30)


def test_parses_plain_name_colon_lines():
    scenario = _scenario()
    first, second = scenario.participants[0], scenario.participants[1]
    text = f"{first.name}: Let's start.\n{second.name}: Sure, go ahead."

    lines = parse_dialogue(text, scenario)

    assert [line.speaker_id for line in lines] == [
        first.speaker_id,
        second.speaker_id,
    ]
    assert lines[0].text == "Let's start."


def test_parses_bold_and_bracketed_names():
    scenario = _scenario()
    name = scenario.participants[0].name
    text = f"**{name}:** Bold speaker.\n[{name}]: Bracketed speaker."

    lines = parse_dialogue(text, scenario)

    assert len(lines) == 2
    assert all(line.speaker_id == scenario.participants[0].speaker_id for line in lines)


def test_first_name_alone_still_resolves():
    scenario = _scenario()
    person = scenario.participants[0]
    lines = parse_dialogue(f"{person.name.split(' ')[0]}: Just the first name.", scenario)
    assert lines[0].speaker_id == person.speaker_id


def test_headings_and_stage_directions_are_dropped():
    scenario = _scenario()
    name = scenario.participants[0].name
    text = "# Meeting notes\n(everyone laughs)\n" f"{name}: Real line."

    lines = parse_dialogue(text, scenario)

    assert len(lines) == 1
    assert lines[0].text == "Real line."


def test_unattributed_continuation_joins_the_previous_turn():
    scenario = _scenario()
    name = scenario.participants[0].name
    lines = parse_dialogue(f"{name}: First part\nand the rest of it.", scenario)

    assert len(lines) == 1
    assert lines[0].text == "First part and the rest of it."


def test_leading_text_without_a_speaker_is_discarded():
    scenario = _scenario()
    name = scenario.participants[0].name
    lines = parse_dialogue(f"Some narration.\n{name}: Attributed.", scenario)

    assert len(lines) == 1
    assert lines[0].text == "Attributed."


def test_build_produces_monotonic_timed_segments():
    scenario = _scenario()
    people = scenario.participants
    text = "\n".join(
        f"{person.name}: This is turn number {index} with several words in it."
        for index, person in enumerate(people)
    )
    result = build_transcript_result(scenario, parse_dialogue(text, scenario))

    assert result.segments
    assert result.duration_seconds > 0
    previous_end = -1.0
    for segment in result.segments:
        assert segment.start < segment.end
        assert segment.start >= previous_end
        previous_end = segment.end
        assert segment.words
        assert segment.words[0].start >= segment.start
        assert segment.words[-1].end <= segment.end + 0.01


def test_speakers_map_only_contains_speakers_that_spoke():
    scenario = _scenario()
    person = scenario.participants[0]
    result = build_transcript_result(
        scenario, parse_dialogue(f"{person.name}: Only I spoke.", scenario)
    )

    assert set(result.speakers) == {person.speaker_id}
    assert result.speakers[person.speaker_id] == person.name


def test_result_survives_a_json_round_trip():
    scenario = _scenario()
    text = "\n".join(
        f"{person.name}: Something worth saying here." for person in scenario.participants
    )
    result = build_transcript_result(scenario, parse_dialogue(text, scenario))

    restored = result_from_payload(result_to_payload(result))

    assert restored.speakers == result.speakers
    assert len(restored.segments) == len(result.segments)
    assert restored.segments[0].text == result.segments[0].text
    assert restored.duration_seconds == result.duration_seconds


def test_summary_source_renders_the_synthetic_transcript():
    scenario = _scenario()
    person = scenario.participants[0]
    result = build_transcript_result(
        scenario, parse_dialogue(f"{person.name}: A line for the notes.", scenario)
    )

    source = render_summary_source(result)

    assert person.name in source
    assert "A line for the notes." in source
    assert transcript_word_count(result) == 5


def test_timings_are_reproducible_for_a_seed():
    scenario = _scenario()
    text = "\n".join(f"{p.name}: Line for {p.name}." for p in scenario.participants)
    lines = parse_dialogue(text, scenario)

    first = build_transcript_result(scenario, lines, seed=8)
    second = build_transcript_result(scenario, lines, seed=8)

    assert [segment.start for segment in first.segments] == [
        segment.start for segment in second.segments
    ]
