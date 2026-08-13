"""The PDF export options: registry, layout effects, persistence, and wiring.

The options are registry-driven so the export dialog, the settings, and both
PDF engines stay in agreement. These tests pin the registry's invariants, the
cover-page toggle's effect on each renderer, and the plumbing that carries the
user's choices from the settings through the worker to the exporters.
"""

from __future__ import annotations

import json

import pytest

from speaker_transcriber.config import AppSettings, SettingsStore
from speaker_transcriber.export.meeting_document import parse_meeting_markdown
from speaker_transcriber.export.pdf_layout import COMPACT, COVER, MASTHEAD, layout_for
from speaker_transcriber.export.pdf_options import (
    COVER_PAGE_OPTION,
    PDF_OPTIONS,
    applicable_pdf_options,
    apply_pdf_options,
    effective_pdf_options,
    pdf_option_defaults,
    pdf_option_deviations,
)
from speaker_transcriber.export.pdf_exporter import (
    export_meeting_pdf,
    reportlab_available,
)
from speaker_transcriber.export.weasyprint_exporter import meeting_document_html


MEETING_MARKDOWN = """# Weekly Sync

*One line about the meeting.*

**Participants:** Alex, Sam

## Executive Summary

The overview paragraph.

## Action Items

| Owner | Action | Priority |
| --- | --- | --- |
| Alex | Ship the build | High |

## Rollout Discussion

- Alex: staged rollout starts Monday.

## Closing Assessment

Solid progress.
"""


# ---------------------------------------------------------------------------
# Registry invariants


def test_option_ids_are_unique() -> None:
    ids = [option.option_id for option in PDF_OPTIONS]
    assert len(ids) == len(set(ids))


def test_options_declare_labels_and_descriptions() -> None:
    for option in PDF_OPTIONS:
        assert option.option_id.strip()
        assert option.label.strip()
        assert option.description.strip()


def test_cover_page_option_defaults_on_and_targets_cover_layouts() -> None:
    (cover,) = [
        option for option in PDF_OPTIONS if option.option_id == COVER_PAGE_OPTION
    ]
    assert cover.default is True
    assert cover.needs_front_matter == (COVER,)


# ---------------------------------------------------------------------------
# Normalization helpers


def test_effective_options_fill_defaults_and_drop_junk() -> None:
    assert effective_pdf_options(None) == pdf_option_defaults()
    values = effective_pdf_options(
        {COVER_PAGE_OPTION: False, "bogus": True, "also_bad": "yes"}
    )
    assert values[COVER_PAGE_OPTION] is False
    assert set(values) == set(pdf_option_defaults())


def test_effective_options_ignore_non_boolean_values() -> None:
    values = effective_pdf_options({COVER_PAGE_OPTION: "false"})
    assert values[COVER_PAGE_OPTION] is True


def test_deviations_keep_only_non_default_choices() -> None:
    assert pdf_option_deviations(None) == {}
    assert pdf_option_deviations({COVER_PAGE_OPTION: True}) == {}
    assert pdf_option_deviations({COVER_PAGE_OPTION: False, "bogus": False}) == {
        COVER_PAGE_OPTION: False
    }


def test_applicable_options_follow_the_style_layout() -> None:
    for style_id in ("meeting_summary", "technical_meeting", "pitch_deck"):
        ids = [option.option_id for option in applicable_pdf_options(style_id)]
        assert COVER_PAGE_OPTION in ids, style_id
    for style_id in ("internal_newsletter", "standup_meeting", "pure_transcription"):
        assert applicable_pdf_options(style_id) == (), style_id


# ---------------------------------------------------------------------------
# Layout effects


def test_disabling_the_cover_turns_a_cover_layout_compact() -> None:
    layout = layout_for("meeting_summary")
    assert layout.front_matter == COVER
    adjusted = apply_pdf_options(layout, {COVER_PAGE_OPTION: False})
    assert adjusted.front_matter == COMPACT
    assert not adjusted.has_cover_page
    assert adjusted.kicker == layout.kicker


def test_enabled_or_missing_options_leave_the_layout_alone() -> None:
    layout = layout_for("meeting_summary")
    assert apply_pdf_options(layout, None) is layout
    assert apply_pdf_options(layout, {COVER_PAGE_OPTION: True}) is layout


def test_disabling_the_cover_does_not_touch_other_front_matter() -> None:
    layout = layout_for("internal_newsletter")
    assert layout.front_matter == MASTHEAD
    assert apply_pdf_options(layout, {COVER_PAGE_OPTION: False}) is layout


# ---------------------------------------------------------------------------
# Renderers honor the toggle


def test_html_renders_a_cover_by_default() -> None:
    document = parse_meeting_markdown(MEETING_MARKDOWN)
    html_text = meeting_document_html(document, style="meeting_summary")
    assert "<header class='cover'>" in html_text
    assert "@page :first" in html_text


def test_html_renders_a_compact_heading_without_the_cover() -> None:
    document = parse_meeting_markdown(MEETING_MARKDOWN)
    html_text = meeting_document_html(
        document,
        style="meeting_summary",
        options={COVER_PAGE_OPTION: False},
    )
    assert "<header class='doc-header compact'>" in html_text
    assert "class='cover'" not in html_text
    assert "@page :first" not in html_text


@pytest.mark.skipif(not reportlab_available(), reason="ReportLab is not installed")
def test_reportlab_export_honors_the_cover_toggle(tmp_path) -> None:
    from speaker_transcriber.export import pdf_exporter

    document = parse_meeting_markdown(MEETING_MARKDOWN)

    with_cover = tmp_path / "with_cover.pdf"
    export_meeting_pdf(document, with_cover, style="meeting_summary")
    assert with_cover.read_bytes().startswith(b"%PDF")
    assert pdf_exporter._NumberedCanvas.bare_pages == 1

    without_cover = tmp_path / "without_cover.pdf"
    export_meeting_pdf(
        document,
        without_cover,
        style="meeting_summary",
        options={COVER_PAGE_OPTION: False},
    )
    assert without_cover.read_bytes().startswith(b"%PDF")
    assert pdf_exporter._NumberedCanvas.bare_pages == 0


# ---------------------------------------------------------------------------
# Settings persistence


def test_settings_validation_keeps_only_known_deviations() -> None:
    settings = AppSettings(
        pdf_options={COVER_PAGE_OPTION: False, "bogus": False, "other": 3}
    )
    settings.validate()
    assert settings.pdf_options == {COVER_PAGE_OPTION: False}


def test_settings_validation_drops_default_and_malformed_values() -> None:
    settings = AppSettings(pdf_options={COVER_PAGE_OPTION: True})
    settings.validate()
    assert settings.pdf_options == {}

    settings = AppSettings(pdf_options="nonsense")
    settings.validate()
    assert settings.pdf_options == {}


def test_settings_round_trip_through_the_store(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    store.save(AppSettings(pdf_options={COVER_PAGE_OPTION: False}))
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["pdf_options"] == {COVER_PAGE_OPTION: False}
    assert store.load().pdf_options == {COVER_PAGE_OPTION: False}


# ---------------------------------------------------------------------------
# Worker plumbing


class FakeSignal:
    def __init__(self) -> None:
        self.payloads: list[object] = []

    def emit(self, *payload: object) -> None:
        self.payloads.append(payload)


def make_worker(tmp_path, markdown: str, style: str):
    from speaker_transcriber.ui.worker import PdfExportWorker

    worker = PdfExportWorker.__new__(PdfExportWorker)
    worker.destination = str(tmp_path / "notes.pdf")
    worker.transcript_text = "Alex: we shipped."
    worker.existing_markdown = markdown
    worker.model_name = ""
    worker.num_ctx = 0
    worker.pdf_engine = "reportlab"
    worker.pdf_theme = "light"
    worker.style = style
    for name in ("progress", "chunk", "section_break", "summary_ready", "completed"):
        setattr(worker, name, FakeSignal())
    return worker


def test_pdf_worker_passes_the_options_to_the_exporter(monkeypatch, tmp_path) -> None:
    exported: dict[str, object] = {}

    def fake_export(
        document, path, engine="reportlab", theme="light", style=None, options=None
    ):
        exported["options"] = options

    monkeypatch.setattr(
        "speaker_transcriber.export.pdf_exporter.export_meeting_pdf",
        fake_export,
    )

    worker = make_worker(tmp_path, MEETING_MARKDOWN, "meeting_summary")
    worker._export()
    assert exported["options"] is None

    worker.pdf_options = {COVER_PAGE_OPTION: False}
    worker._export()
    assert exported["options"] == {COVER_PAGE_OPTION: False}
