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
