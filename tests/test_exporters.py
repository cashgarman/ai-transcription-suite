import json

from speaker_transcriber.export.common import speaker_color_map
from speaker_transcriber.export.csv_exporter import render_csv
from speaker_transcriber.export.json_exporter import from_json_dict, render_json, to_json_dict
from speaker_transcriber.export.markdown_exporter import render_markdown
from speaker_transcriber.export.subtitle_exporter import render_srt, render_vtt
from speaker_transcriber.export.text_exporter import render_text
from speaker_transcriber.pipeline.types import TranscriptResult, TranscriptSegment, Word


def sample_result() -> TranscriptResult:
    word = Word("Welcome", 2.1, 2.6, "SPEAKER_00")
    segment = TranscriptSegment(
        2.1,
        6.4,
        "SPEAKER_00",
        "Welcome.",
        [word],
    )
    return TranscriptResult(
        source_file="meeting.mp4",
        language="en",
        duration_seconds=123.45,
        speakers={"SPEAKER_00": "Speaker 1"},
        segments=[segment],
    )


def test_speaker_color_map_assigns_stable_colors() -> None:
    result = sample_result()
    colors = speaker_color_map(result)
    assert colors["SPEAKER_00"] == "#4FC3F7"
    assert len(colors) == 1

    output = render_text(sample_result())
    assert "[00:00:02 - 00:00:06] Speaker 1" in output
    assert "Welcome." in output


def test_json_schema() -> None:
    payload = json.loads(render_json(sample_result()))
    assert payload["source_file"] == "meeting.mp4"
    assert payload["segments"][0]["words"][0]["word"] == "Welcome"
    assert payload["speakers"]["SPEAKER_00"] == "Speaker 1"
    assert payload["alignment_available"] is False
    assert payload["diarization_available"] is False


def test_from_json_dict_matches_sample_result() -> None:
    restored = from_json_dict(to_json_dict(sample_result()))
    assert restored.source_file == "meeting.mp4"
    assert restored.speakers["SPEAKER_00"] == "Speaker 1"


def test_markdown_format() -> None:
    output = render_markdown(sample_result())
    assert "# Transcript: meeting.mp4" in output
    assert "## Speaker 1" in output


def test_subtitle_formats() -> None:
    assert "00:00:02,100 --> 00:00:06,400" in render_srt(sample_result())
    assert "WEBVTT" in render_vtt(sample_result())
    assert "<v Speaker 1>Welcome." in render_vtt(sample_result())


def test_csv_format() -> None:
    lines = render_csv(sample_result()).splitlines()
    assert lines[0] == "start,end,speaker,text"
    assert lines[1] == "2.100,6.400,Speaker 1,Welcome."
