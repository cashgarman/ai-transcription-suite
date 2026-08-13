"""The per-style section registry, exclusion plumbing, and document stripping.

Users can turn individual sections of a summary off before it is written. The
registry on each SummaryStyle drives everything: the dialog options, the
override directive injected into the document-shaping prompts, the
deterministic strip of the finished Markdown, settings validation, and the
PDF format-pass requirements.
"""

from __future__ import annotations

import json
import re

import pytest

from speaker_transcriber.config import AppSettings, SettingsStore
from speaker_transcriber.export.meeting_document import parse_meeting_markdown
from speaker_transcriber.models.section_filter import (
    move_sections_to_end,
    normalize_heading,
    strip_excluded_sections,
)
from speaker_transcriber.models.summarization import RequirementsSummarizer
from speaker_transcriber.prompts import (
    MEETING_PIPELINE,
    SEGMENT_NOTES_SECTION_ID,
    SEQUENTIAL_PIPELINE,
    SUMMARY_STYLES,
    excluded_section_headings,
    get_prompt,
    get_style,
    load_prompts,
    normalize_excluded_sections,
    style_sections,
)


def prompt_text(name: str, style_id: str) -> str:
    return re.sub(r"\s+", " ", get_prompt(name, style_id))


class FakeChunk:
    def __init__(self, response: str = "") -> None:
        self.response = response
        self.thinking = ""


class RecordingClient:
    def __init__(self, outputs: list[str] | None = None) -> None:
        self.outputs = list(outputs or [])
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        text = self.outputs.pop(0) if self.outputs else "ok"
        yield FakeChunk(response=text)


def make_summarizer(
    client: object,
    style: str,
    excluded: tuple[str, ...] = (),
    num_ctx: int = 8192,
) -> RequirementsSummarizer:
    summarizer = RequirementsSummarizer.__new__(RequirementsSummarizer)
    summarizer.model_name = "test-model"
    summarizer.num_ctx = num_ctx
    summarizer.style = get_style(style)
    summarizer.excluded_sections = normalize_excluded_sections(style, excluded)
    summarizer.cancel_event = None
    summarizer.client = client
    return summarizer


# ---------------------------------------------------------------------------
# The registry


def test_sequential_styles_offer_no_sections() -> None:
    for style in SUMMARY_STYLES:
        if style.pipeline == SEQUENTIAL_PIPELINE:
            assert style.sections == ()


def test_every_other_style_offers_sections() -> None:
    for style in SUMMARY_STYLES:
        if style.pipeline != SEQUENTIAL_PIPELINE:
            assert style.sections, f"{style.style_id} registers no sections"


def test_section_ids_are_unique_within_each_style() -> None:
    for style in SUMMARY_STYLES:
        ids = [section.section_id for section in style.sections]
        assert len(ids) == len(set(ids)), f"{style.style_id} repeats a section id"


def test_sections_declare_labels_descriptions_and_headings() -> None:
    """Only the structural detailed-notes section may go without headings."""
    for style in SUMMARY_STYLES:
        for section in style.sections:
            assert section.label.strip()
            assert section.description.strip()
            assert section.headings or section.section_id == SEGMENT_NOTES_SECTION_ID
            assert all(heading.strip() for heading in section.headings)


def test_primary_headings_match_the_merge_prompt() -> None:
    """The first heading of every section is the one its merge prompt asks for."""
    load_prompts()
    for style in SUMMARY_STYLES:
        if not style.sections:
            continue
        merge = prompt_text("merge", style.style_id)
        for section in style.sections:
            if not section.headings:
                continue
            assert f"## {section.headings[0]}" in merge, (
                f"{style.style_id}: `## {section.headings[0]}` is not in its "
                "merge prompt"
            )


def test_meeting_styles_offer_the_detailed_notes_toggle() -> None:
    """Exactly the styles that append segment notes can turn them off."""
    for style in SUMMARY_STYLES:
        ids = {section.section_id for section in style.sections}
        if style.pipeline == MEETING_PIPELINE:
            assert SEGMENT_NOTES_SECTION_ID in ids, style.style_id
            assert style.trailing_sections == ("Closing Assessment",)
        else:
            assert SEGMENT_NOTES_SECTION_ID not in ids, style.style_id
            assert style.trailing_sections == ()


def test_sections_default_to_included() -> None:
    for style in SUMMARY_STYLES:
        for section in style.sections:
            assert section.default_included


def test_normalize_excluded_sections_keeps_known_ids_in_registry_order() -> None:
    result = normalize_excluded_sections(
        "meeting_summary",
        ["closing_assessment", "made_up", "action_items"],
    )
    assert result == ("action_items", "closing_assessment")


def test_excluded_section_headings_flatten_every_alias() -> None:
    headings = excluded_section_headings("meeting_summary", ["action_items"])
    assert headings == ("Action Items", "Additional Action Items")


def test_requires_action_table_flips_only_on_action_items() -> None:
    style = get_style("meeting_summary")
    assert style.requires_action_table(())
    assert style.requires_action_table(("closing_assessment",))
    assert not style.requires_action_table(("action_items",))


# ---------------------------------------------------------------------------
# Deterministic stripping


DOCUMENT = """# Weekly Sync

*One line.*

**Participants:** Alex, Jordan

## Executive Summary

The overview paragraph.

## Action Items

| Owner | Action | Priority |
| --- | --- | --- |
| Alex | Ship it | High |

## Open Questions

- Who owns the rollout?

## Closing Assessment

Solid progress.

## Additional Action Items

- Jordan: file the ticket.
"""


def test_strip_removes_the_section_heading_and_body() -> None:
    result = strip_excluded_sections(
        DOCUMENT, ("Action Items", "Additional Action Items")
    )
    assert "Action Items" not in result
    assert "Ship it" not in result
    assert "file the ticket" not in result
    assert "## Executive Summary" in result
    assert "Who owns the rollout?" in result
    assert "## Closing Assessment" in result


def test_strip_matches_headings_case_insensitively_and_ignores_colons() -> None:
    text = "## ACTION ITEMS:\n\n- do it\n\n## Kept\n\nstays"
    result = strip_excluded_sections(text, ("Action Items",))
    assert "do it" not in result
    assert "stays" in result


def test_strip_takes_subsections_of_an_excluded_section_with_it() -> None:
    text = (
        "# Record\n\n## Options Considered\n\n### Option A\n\npros\n\n"
        "### Option B\n\ncons\n\n## Decision\n\nUse B."
    )
    result = strip_excluded_sections(text, ("Options Considered",))
    assert "Option A" not in result
    assert "pros" not in result
    assert "## Decision" in result
    assert "Use B." in result


def test_strip_stops_at_a_top_level_heading() -> None:
    text = "## Shoutouts\n\n- praise\n\n# Next Document\n\nbody"
    result = strip_excluded_sections(text, ("Shoutouts",))
    assert "praise" not in result
    assert "# Next Document" in result
    assert "body" in result


def test_strip_without_targets_returns_the_text_unchanged() -> None:
    assert strip_excluded_sections(DOCUMENT, ()) == DOCUMENT


def test_strip_leaves_unrelated_documents_alone() -> None:
    result = strip_excluded_sections(DOCUMENT, ("Team Themes",))
    assert "## Executive Summary" in result
    assert "Ship it" in result


def test_normalize_heading_removes_emphasis_case_and_colons() -> None:
    assert normalize_heading("**Action Items:**") == "action items"
    assert normalize_heading("  What's   Next  ") == "what's next"


# ---------------------------------------------------------------------------
# Trailing-section relocation


def test_move_sections_to_end_puts_the_closing_after_the_notes() -> None:
    result = move_sections_to_end(DOCUMENT, ("Closing Assessment",))
    assert result.index("## Closing Assessment") > result.index(
        "## Additional Action Items"
    )
    assert result.rstrip().endswith("Solid progress.")
    assert "## Executive Summary" in result
    assert "Ship it" in result


def test_move_sections_to_end_is_stable_when_already_last() -> None:
    relocated = move_sections_to_end(DOCUMENT, ("Closing Assessment",))
    assert move_sections_to_end(relocated, ("Closing Assessment",)) == relocated


def test_move_sections_to_end_without_a_match_returns_the_text() -> None:
    assert move_sections_to_end(DOCUMENT, ("Team Themes",)) == DOCUMENT
    assert move_sections_to_end(DOCUMENT, ()) == DOCUMENT


# ---------------------------------------------------------------------------
# Prompt injection


def test_stage_prompts_carry_the_directive_only_when_sections_are_excluded() -> None:
    load_prompts()
    plain = make_summarizer(RecordingClient(), "meeting_summary")
    excluding = make_summarizer(
        RecordingClient(), "meeting_summary", ("action_items",)
    )
    for stage in ("merge", "validate", "format"):
        base = get_prompt(stage, "meeting_summary")
        assert plain._prompt(stage) == base
        injected = excluding._prompt(stage)
        assert injected.startswith(base)
        assert "Sections turned off by the user" in injected
        assert "`## Action Items`" in injected
    for stage in ("system", "chunk"):
        assert excluding._prompt(stage) == get_prompt(stage, "meeting_summary")


def test_required_sections_shrink_with_the_exclusions() -> None:
    summarizer = make_summarizer(
        RecordingClient(), "meeting_summary", ("action_items",)
    )
    assert summarizer._required_sections() == ("open questions",)
    summarizer = make_summarizer(RecordingClient(), "meeting_summary")
    assert summarizer._required_sections() == ("action items", "open questions")


def test_constructor_normalizes_unknown_section_ids(monkeypatch) -> None:
    import sys
    import types

    fake_ollama = types.SimpleNamespace(Client=lambda: RecordingClient())
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)
    summarizer = RequirementsSummarizer(
        "test-model",
        num_ctx=8192,
        style="meeting_summary",
        excluded_sections=("bogus", "closing_assessment"),
    )
    assert summarizer.excluded_sections == ("closing_assessment",)


# ---------------------------------------------------------------------------
# End-to-end through the summarizer


EXTRACT = (
    "## Rollout planning\n\n"
    "- Alex: staged rollout starts Monday.\n\n"
    "## Action items\n\n"
    "- Alex: ship the build. (High)\n\n"
    "## Questions\n\n"
    "- Who owns the rollout?\n"
)

MERGED = (
    "# Rollout Planning\n\n"
    "*Staged rollout starts Monday.*\n\n"
    "**Participants:** Alex\n\n"
    "**Primary topics:** rollout\n\n"
    "## Executive Summary\n\nThe team planned the rollout.\n\n"
    "## Key Decisions and Direction\n\n1. Start Monday.\n\n"
    "## Action Items\n\n"
    "| Owner | Action | Priority |\n| --- | --- | --- |\n"
    "| Alex | Ship the build | High |\n\n"
    "## Open Questions\n\n- Who owns the rollout?\n\n"
    "## Closing Assessment\n\nOn track.\n"
)


def test_summarize_strips_excluded_sections_the_model_still_wrote() -> None:
    """Even when the model ignores the directive, the sections are removed."""
    load_prompts()
    client = RecordingClient([EXTRACT, MERGED, MERGED])
    summarizer = make_summarizer(
        client,
        "meeting_summary",
        ("action_items", "closing_assessment"),
    )
    result = summarizer.summarize("Alex: the rollout starts Monday.")
    assert "## Executive Summary" in result
    assert "Who owns the rollout?" in result
    assert "Action Items" not in result
    assert "Ship the build" not in result
    assert "ship the build" not in result
    assert "Closing Assessment" not in result
    merge_call = client.calls[1]
    assert "Sections turned off by the user" in merge_call["prompt"]


def test_summarize_without_exclusions_keeps_every_section() -> None:
    load_prompts()
    client = RecordingClient([EXTRACT, MERGED, MERGED])
    summarizer = make_summarizer(client, "meeting_summary")
    result = summarizer.summarize("Alex: the rollout starts Monday.")
    assert "## Action Items" in result
    assert "## Closing Assessment" in result
    assert "Sections turned off by the user" not in client.calls[1]["prompt"]


def test_summarize_moves_the_closing_assessment_behind_the_notes() -> None:
    """The closing lands at the very end, after the detailed topic notes."""
    load_prompts()
    client = RecordingClient([EXTRACT, MERGED, MERGED])
    summarizer = make_summarizer(client, "meeting_summary")
    result = summarizer.summarize("Alex: the rollout starts Monday.")
    assert result.index("## Closing Assessment") > result.index(
        "## Rollout planning"
    )
    assert result.rstrip().endswith("On track.")


def test_summarize_can_leave_the_detailed_notes_out() -> None:
    load_prompts()
    client = RecordingClient([EXTRACT, MERGED, MERGED])
    summarizer = make_summarizer(
        client, "meeting_summary", (SEGMENT_NOTES_SECTION_ID,)
    )
    result = summarizer.summarize("Alex: the rollout starts Monday.")
    assert "Rollout planning" not in result
    assert "## Executive Summary" in result
    assert "## Action Items" in result
    assert result.rstrip().endswith("On track.")
    directive = client.calls[1]["prompt"]
    assert "detailed per-topic discussion notes are also turned off" in directive


def test_format_meeting_notes_strips_excluded_sections() -> None:
    load_prompts()
    client = RecordingClient([MERGED])
    summarizer = make_summarizer(client, "meeting_summary", ("action_items",))
    result = summarizer.format_meeting_notes("# Draft\n\nnotes")
    assert "Action Items" not in result
    assert "## Open Questions" in result
    assert "Sections turned off by the user" in client.calls[0]["prompt"]


def test_format_meeting_notes_moves_the_closing_to_the_end() -> None:
    load_prompts()
    wrong_order = (
        "# Weekly Sync\n\n## Executive Summary\n\nOverview.\n\n"
        "## Closing Assessment\n\nSolid.\n\n"
        "## Rollout Discussion\n\n- Alex: staged rollout starts Monday.\n"
    )
    client = RecordingClient([wrong_order])
    summarizer = make_summarizer(client, "meeting_summary")
    result = summarizer.format_meeting_notes("# Draft\n\nnotes")
    assert result.index("## Closing Assessment") > result.index(
        "## Rollout Discussion"
    )
    assert result.rstrip().endswith("Solid.")


# ---------------------------------------------------------------------------
# Settings persistence


def test_settings_validation_drops_unknown_styles_and_ids() -> None:
    settings = AppSettings(
        summary_excluded_sections={
            "meeting_summary": ["action_items", "bogus"],
            "not_a_style": ["action_items"],
            "pitch_deck": "not-a-list",
        }
    )
    settings.validate()
    assert settings.summary_excluded_sections == {
        "meeting_summary": ["action_items"]
    }


def test_settings_validation_resets_a_non_dict_value() -> None:
    settings = AppSettings(summary_excluded_sections="nope")
    settings.validate()
    assert settings.summary_excluded_sections == {}


def test_settings_round_trip_through_the_store(tmp_path) -> None:
    store = SettingsStore(tmp_path)
    settings = AppSettings(
        summary_excluded_sections={
            "casual_meeting": ["risks", "closing_assessment"]
        }
    )
    store.save(settings)
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["summary_excluded_sections"] == {
        "casual_meeting": ["risks", "closing_assessment"]
    }
    loaded = store.load()
    assert loaded.summary_excluded_sections == {
        "casual_meeting": ["risks", "closing_assessment"]
    }


# ---------------------------------------------------------------------------
# PDF format-pass interaction


TABLELESS_MEETING = """# Weekly Sync

*One line.*

## Executive Summary

The overview.

## Open Questions

- Who owns the rollout?
"""


def test_needs_format_pass_can_waive_the_action_table() -> None:
    document = parse_meeting_markdown(TABLELESS_MEETING)
    assert document.needs_format_pass()
    assert not document.needs_format_pass(require_action_table=False)
    untitled = parse_meeting_markdown("Some loose text without headings.")
    assert untitled.needs_format_pass(require_action_table=False)


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


def test_pdf_worker_skips_the_format_pass_when_action_items_are_off(
    monkeypatch, tmp_path
) -> None:
    exported: dict[str, object] = {}

    def fake_export(
        document, path, engine="reportlab", theme="light", style=None, options=None
    ):
        exported["style"] = style

    monkeypatch.setattr(
        "speaker_transcriber.export.pdf_exporter.export_meeting_pdf",
        fake_export,
    )

    worker = make_worker(tmp_path, TABLELESS_MEETING, "meeting_summary")

    with pytest.raises(RuntimeError, match="need formatting"):
        worker._export()

    worker.excluded_sections = ("action_items",)
    worker._export()
    assert exported["style"] == "meeting_summary"


MISORDERED_MEETING = """# Weekly Sync

*One line.*

## Executive Summary

The overview.

## Action Items

| Owner | Action | Priority |
| --- | --- | --- |
| Alex | Ship it | High |

## Closing Assessment

Solid progress.

## Rollout Discussion

- Alex: staged rollout starts Monday.
"""


def test_pdf_export_moves_the_closing_behind_cached_notes(
    monkeypatch, tmp_path
) -> None:
    """Summaries written before the order change export with the closing last."""
    exported: dict[str, object] = {}

    def fake_export(
        document, path, engine="reportlab", theme="light", style=None, options=None
    ):
        exported["document"] = document

    monkeypatch.setattr(
        "speaker_transcriber.export.pdf_exporter.export_meeting_pdf",
        fake_export,
    )
    worker = make_worker(tmp_path, MISORDERED_MEETING, "meeting_summary")
    worker._export()

    document = exported["document"]
    titles = [section.title for section in document.named_sections()]
    assert titles[-1] == "Closing Assessment"
    assert "Rollout Discussion" in titles
    (relocated,) = worker.summary_ready.payloads[0]
    assert relocated.index("## Closing Assessment") > relocated.index(
        "## Rollout Discussion"
    )
