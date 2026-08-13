from pathlib import Path

import pytest

from speaker_transcriber.export.meeting_document import (
    ActionTableBlock,
    NumberedListBlock,
    RiskListBlock,
    is_usable_summary_markdown,
    parse_meeting_markdown,
)
from speaker_transcriber.export.pdf_exporter import export_meeting_pdf


COMPLETE_MARKDOWN = """
# Sound Project Integration and Game Development Planning

*The team discussed sound integration, MVP scope, and publisher pitching.*

**Participants:** Brian, Andrew, Cash, Ronny, Benny, and other team members

**Primary topics:** Sound integration, workflow, MVP scope, destruction, animation

## Executive Summary

The team discussed how sound, engineering workflow, and presentation should support the project.

Cash proposed controlled feature branches.

## Key Decisions and Direction

1. Controlled branching: Use feature or bug branches and merge into main only after QA validation.
2. Buddy reviews: Use a second reviewer for difficult or high-risk merges.
3. Simple destruction MVP: Use a state-based solution; defer voxel experimentation.

## Sound Integration

Andrew described a music background and current focus on sound-design work.

## Action Items

| Owner | Action | Priority |
| --- | --- | --- |
| Brian | Confirm Levi's participation in Tuesday's 10:00 AM PST meeting | High |
| Cash | Support branching, merge, and integration questions until Seba returns | High |
| Team | Adopt feature/bug branches and QA-gated merges | High |

## Open Questions

- Is the Tuesday meeting confirmed, and will Levi be available?
- What exact destruction states are required for the MVP?

## Risks, Dependencies, and Blockers

Limited voxel expertise: Complex destruction may miss the milestone.

Mitigation: Use a state-based MVP solution.

Limited schedule: Advanced systems may not be proven in time.

Mitigation: Focus on a vertical slice and core experience.

## Closing Assessment

The meeting aligned the team around a pragmatic strategy.
""".strip()


def test_parse_complete_meeting_markdown() -> None:
    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    assert document.title == "Sound Project Integration and Game Development Planning"
    assert "sound integration" in document.subtitle.lower()
    assert "Brian" in document.participants
    assert "Cash" in document.participants
    assert "destruction" in document.primary_topics
    titles = [section.title for section in document.named_sections()]
    assert "Executive Summary" in titles
    assert "Key Decisions and Direction" in titles
    assert "Action Items" in titles
    assert "Closing Assessment" in titles

    decisions = next(
        section for section in document.sections
        if section.title == "Key Decisions and Direction"
    )
    numbered = [
        block for block in decisions.blocks if isinstance(block, NumberedListBlock)
    ]
    assert numbered
    assert any("Controlled branching" in item for item in numbered[0].items)

    action_section = next(
        section for section in document.sections if section.title == "Action Items"
    )
    tables = [
        block for block in action_section.blocks if isinstance(block, ActionTableBlock)
    ]
    assert tables
    owners = [row.owner for row in tables[0].rows]
    assert owners == ["Brian", "Cash", "Team"]
    assert tables[0].rows[0].priority == "High"
    assert "Levi" in tables[0].rows[0].action

    risks = next(
        section for section in document.sections if "Risk" in section.title
    )
    risk_blocks = [
        block for block in risks.blocks if isinstance(block, RiskListBlock)
    ]
    assert risk_blocks
    assert any("voxel" in item.text.lower() for item in risk_blocks[0].items)
    assert any(
        "state-based" in item.mitigation.lower() for item in risk_blocks[0].items
    )
    assert not document.needs_format_pass()


def test_incomplete_markdown_needs_format_pass() -> None:
    document = parse_meeting_markdown(
        "Some notes from the call.\n\nWe talked about stuff."
    )
    assert document.needs_format_pass()
    assert not document.has_action_table()


def test_missing_action_table_needs_format_pass() -> None:
    markdown = """
# Weekly Sync

*Status update.*

**Participants:** Alex

## Executive Summary

The team reviewed progress.

## Next Steps

Keep going.
""".strip()
    document = parse_meeting_markdown(markdown)
    assert document.title == "Weekly Sync"
    assert document.named_sections()
    assert document.needs_format_pass()


def test_participants_sentence_is_not_metadata() -> None:
    markdown = """
# Title

*Subtitle here.*

Participants were aligned on the plan.

## Executive Summary

Discussion continued.

## Action Items

| Owner | Action | Priority |
| --- | --- | --- |
| Alex | Follow up | High |
""".strip()
    document = parse_meeting_markdown(markdown)
    assert document.participants == ""
    untitled = [section for section in document.sections if not section.title]
    assert untitled
    assert not document.needs_format_pass()
    assert is_usable_summary_markdown(COMPLETE_MARKDOWN)
    assert not is_usable_summary_markdown("")
    assert not is_usable_summary_markdown("Generating summary…")
    assert not is_usable_summary_markdown("Summary failed: Ollama is down")
    assert not is_usable_summary_markdown(
        "An optional local Ollama summary will appear here."
    )


def test_export_meeting_pdf_writes_pdf_header(tmp_path) -> None:
    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    path = tmp_path / "meeting.pdf"
    export_meeting_pdf(document, path)
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 500


def test_export_meeting_pdf_dispatches_weasyprint(monkeypatch, tmp_path) -> None:
    called: dict[str, object] = {}

    def fake_export(document, path, theme="light") -> None:
        called["document"] = document
        called["path"] = path
        called["theme"] = theme

    monkeypatch.setattr(
        "speaker_transcriber.export.weasyprint_exporter.weasyprint_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "speaker_transcriber.export.weasyprint_exporter.export_weasyprint_pdf",
        fake_export,
    )
    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    path = tmp_path / "meeting.pdf"
    export_meeting_pdf(document, path, engine="weasyprint")
    assert called["path"] == path
    assert called["document"] is document
    assert not path.exists()


def test_weasyprint_falls_back_to_reportlab_when_unavailable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "speaker_transcriber.export.weasyprint_exporter.weasyprint_available",
        lambda: False,
    )
    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    path = tmp_path / "meeting.pdf"
    export_meeting_pdf(document, path, engine="weasyprint")
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 500


def test_weasyprint_runtime_error_falls_back_to_reportlab(monkeypatch, tmp_path) -> None:
    def boom(document, path, theme="light") -> None:
        raise RuntimeError(
            "WeasyPrint is not available. Install it and its native libraries "
            "(Pango/Cairo/GTK), or switch Format PDF notes to ReportLab."
        )

    monkeypatch.setattr(
        "speaker_transcriber.export.weasyprint_exporter.weasyprint_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "speaker_transcriber.export.weasyprint_exporter.export_weasyprint_pdf",
        boom,
    )
    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    path = tmp_path / "meeting.pdf"
    export_meeting_pdf(document, path, engine="weasyprint")
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 500


def test_missing_reportlab_explains_install(monkeypatch, tmp_path) -> None:
    import speaker_transcriber.export.pdf_exporter as pdf_exporter

    monkeypatch.setattr(pdf_exporter, "_REPORTLAB_READY", False)
    monkeypatch.setattr(pdf_exporter, "reportlab_available", lambda: False)
    monkeypatch.setattr(
        "speaker_transcriber.export.weasyprint_exporter.weasyprint_available",
        lambda: False,
    )

    real_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "reportlab" or name.startswith("reportlab."):
            raise ImportError("No module named 'reportlab'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    try:
        export_meeting_pdf(document, tmp_path / "meeting.pdf", engine="reportlab")
    except RuntimeError as exc:
        assert "pip install reportlab" in str(exc)
        assert "WeasyPrint" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_weasyprint_html_includes_title() -> None:
    from speaker_transcriber.export.weasyprint_exporter import meeting_document_html

    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    html = meeting_document_html(document)
    assert "<h1>Sound Project Integration and Game Development Planning</h1>" in html
    assert "<table>" in html


def test_configure_weasyprint_libraries_discovers_gobject(tmp_path, monkeypatch) -> None:
    import os

    from speaker_transcriber.export import weasyprint_exporter as module

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "libgobject-2.0-0.dll").write_bytes(b"")
    monkeypatch.setattr(module, "_DEFAULT_DLL_DIRS", (bin_dir,))
    monkeypatch.delenv("WEASYPRINT_DLL_DIRECTORIES", raising=False)
    found = module.configure_weasyprint_libraries()
    assert str(bin_dir) in found
    assert str(bin_dir) in os.environ["WEASYPRINT_DLL_DIRECTORIES"]


def test_toc_entries_cover_named_sections() -> None:
    from speaker_transcriber.export.pdf_theme import toc_entries

    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    entries = toc_entries(document)
    titles = [entry.title for entry in entries if entry.level == 1]
    assert "Executive Summary" in titles
    assert "Action Items" in titles
    assert "Closing Assessment" in titles
    anchors = [entry.anchor for entry in entries]
    assert "sec-executive-summary" in anchors
    assert len(anchors) == len(set(anchors))


def test_weasyprint_html_has_clickable_table_of_contents() -> None:
    from speaker_transcriber.export.weasyprint_exporter import meeting_document_html

    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    html = meeting_document_html(document)
    assert "class='toc'" in html
    assert "Contents" in html
    assert "href='#sec-executive-summary'" in html
    assert 'id="sec-executive-summary"' in html


def test_weasyprint_html_skips_toc_for_single_section() -> None:
    from speaker_transcriber.export.weasyprint_exporter import meeting_document_html

    markdown = "# Short Note\n\n## Executive Summary\n\nOne section only."
    document = parse_meeting_markdown(markdown)
    html = meeting_document_html(document)
    assert "class='toc'" not in html


def test_weasyprint_html_sections_are_divided() -> None:
    from speaker_transcriber.export.weasyprint_exporter import meeting_document_html

    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    html = meeting_document_html(document)
    assert "section divided" in html
    assert "border-top" in html


def test_weasyprint_dark_theme_uses_dark_page() -> None:
    from speaker_transcriber.export.weasyprint_exporter import meeting_document_html

    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    dark = meeting_document_html(document, theme="dark")
    light = meeting_document_html(document)
    assert 'class="theme-dark"' in dark
    assert "#12181C" in dark
    assert "#F4F7F8" in dark
    assert 'class="theme-light"' in light
    assert "#12181C" not in light


def test_weasyprint_unknown_theme_falls_back_to_light() -> None:
    from speaker_transcriber.export.weasyprint_exporter import meeting_document_html

    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    html = meeting_document_html(document, theme="neon")
    assert 'class="theme-light"' in html


def test_reportlab_lists_render_without_list_flowable() -> None:
    import speaker_transcriber.export.pdf_exporter as pdf_exporter
    from speaker_transcriber.export.pdf_theme import palette_for

    pdf_exporter._ensure_reportlab()
    palette = palette_for("light")
    styles = pdf_exporter._styles(palette)
    flowables = pdf_exporter._list_flowables(
        ["First item", "Second item"],
        styles,
        palette,
        numbered=False,
    )
    texts = [
        flowable.text for flowable in flowables if hasattr(flowable, "text")
    ]
    assert len(texts) == 2
    assert all("bullet" not in text for text in texts)
    assert all("\u2022" in text for text in texts)
    assert not hasattr(pdf_exporter, "ListFlowable")


def test_reportlab_numbered_lists_use_digits() -> None:
    import speaker_transcriber.export.pdf_exporter as pdf_exporter
    from speaker_transcriber.export.pdf_theme import palette_for

    pdf_exporter._ensure_reportlab()
    palette = palette_for("light")
    styles = pdf_exporter._styles(palette)
    flowables = pdf_exporter._list_flowables(
        ["First", "Second"],
        styles,
        palette,
        numbered=True,
    )
    texts = [
        flowable.text for flowable in flowables if hasattr(flowable, "text")
    ]
    assert "1." in texts[0]
    assert "2." in texts[1]


def test_export_meeting_pdf_dark_theme_writes_pdf(tmp_path) -> None:
    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    path = tmp_path / "meeting_dark.pdf"
    export_meeting_pdf(document, path, theme="dark")
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 500


def test_export_meeting_pdf_weasyprint_writes_pdf(tmp_path) -> None:
    from speaker_transcriber.export.weasyprint_exporter import weasyprint_available

    if not weasyprint_available():
        pytest.skip("WeasyPrint native libraries are not available")
    document = parse_meeting_markdown(COMPLETE_MARKDOWN)
    path = tmp_path / "meeting.pdf"
    export_meeting_pdf(document, path, engine="weasyprint")
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 500
