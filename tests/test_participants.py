from speaker_transcriber.export.meeting_document import parse_meeting_markdown
from speaker_transcriber.export.participants import (
    ParticipantHighlighter,
    build_highlighter,
    parse_participants,
)
from speaker_transcriber.export.pdf_theme import palette_for


COLORS = ("#111111", "#222222", "#333333")


def _wrap(text: str, color: str) -> str:
    return f"[{color}]{text}[/]"


def test_parse_participants_splits_names_and_drops_placeholders() -> None:
    names = parse_participants(
        "Brian, Andrew, Cash, Ronny, Benny, and other team members"
    )
    assert names == ["Brian", "Andrew", "Cash", "Ronny", "Benny"]


def test_parse_participants_ignores_duplicates_and_blanks() -> None:
    assert parse_participants("Cash, cash, , Cash;  GranSeba") == ["Cash", "GranSeba"]


def test_parse_participants_handles_empty_input() -> None:
    assert parse_participants("") == []
    assert parse_participants("   ") == []


def test_highlighter_colors_each_participant_distinctly() -> None:
    highlighter = build_highlighter("Cash, GranSeba", COLORS)
    result = highlighter.apply("Cash asked GranSeba about the branch.", _wrap)
    assert result == (
        "[#111111]Cash[/] asked [#222222]GranSeba[/] about the branch."
    )


def test_highlighter_matches_similar_spellings() -> None:
    highlighter = build_highlighter("GranSeba", COLORS)
    for variant in ("Gran Seba", "Granseba", "GranSeba's"):
        assert "[#111111]" in highlighter.apply(f"{variant} replied.", _wrap)


def test_highlighter_matches_a_single_name_part() -> None:
    highlighter = build_highlighter("Andrew Miller", COLORS)
    result = highlighter.apply("Andrew described the sound work.", _wrap)
    assert result.startswith("[#111111]Andrew[/]")


def test_highlighter_ignores_unrelated_capitalized_words() -> None:
    highlighter = build_highlighter("Cash, Brian", COLORS)
    result = highlighter.apply("Case studies were reviewed on Tuesday.", _wrap)
    assert result == "Case studies were reviewed on Tuesday."


def test_highlighter_leaves_tags_and_entities_untouched() -> None:
    highlighter = build_highlighter("Cash", COLORS)
    result = highlighter.apply("<b>Cash</b> and Q&amp;A", _wrap)
    assert result == "<b>[#111111]Cash[/]</b> and Q&amp;A"


def test_highlighter_is_inert_without_participants() -> None:
    highlighter = build_highlighter("", COLORS)
    assert not highlighter
    assert highlighter.apply("Cash spoke.", _wrap) == "Cash spoke."
    assert not ParticipantHighlighter()


def test_highlighter_colors_cycle_when_participants_exceed_palette() -> None:
    highlighter = build_highlighter("Ann, Bob, Cid, Dee", ("#AAAAAA", "#BBBBBB"))
    colors = [style.color for style in highlighter.styles]
    assert colors == ["#AAAAAA", "#BBBBBB", "#AAAAAA", "#BBBBBB"]


def test_palettes_define_participant_colors() -> None:
    for theme in ("light", "dark"):
        palette = palette_for(theme)
        assert len(palette.participants) >= 4
        assert len(set(palette.participants)) == len(palette.participants)
    assert palette_for("light").participants != palette_for("dark").participants


MARKDOWN = """
# Weekly Sync

*Status update.*

**Participants:** Cash, GranSeba

## Executive Summary

Cash explained the replay system to GranSeba.

## Action Items

| Owner | Action | Priority |
| --- | --- | --- |
| Cash | Fix boss locomotion | High |
""".strip()


def test_weasyprint_html_bolds_and_colors_participants() -> None:
    from speaker_transcriber.export.weasyprint_exporter import meeting_document_html

    html = meeting_document_html(parse_meeting_markdown(MARKDOWN))
    palette = palette_for("light")
    assert f"class='participant' style='color:{palette.participants[0]}'" in html
    assert f"class='participant' style='color:{palette.participants[1]}'" in html
    assert ".participant { font-weight: 700; }" in html


def test_weasyprint_dark_theme_uses_dark_participant_colors() -> None:
    from speaker_transcriber.export.weasyprint_exporter import meeting_document_html

    document = parse_meeting_markdown(MARKDOWN)
    html = meeting_document_html(document, theme="dark")
    assert palette_for("dark").participants[0] in html
    assert palette_for("light").participants[0] not in html


def test_reportlab_markup_bolds_and_colors_participants() -> None:
    import speaker_transcriber.export.pdf_exporter as pdf_exporter

    highlighter = build_highlighter("Cash, GranSeba", COLORS)
    markup = pdf_exporter._rich("Cash briefed GranSeba.", highlighter)
    assert '<b><font color="#111111">Cash</font></b>' in markup
    assert '<b><font color="#222222">GranSeba</font></b>' in markup


def test_reportlab_export_with_participants_writes_pdf(tmp_path) -> None:
    from speaker_transcriber.export.pdf_exporter import export_meeting_pdf

    document = parse_meeting_markdown(MARKDOWN)
    path = tmp_path / "meeting.pdf"
    export_meeting_pdf(document, path)
    assert path.read_bytes().startswith(b"%PDF")
