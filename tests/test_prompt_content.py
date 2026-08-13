"""Content contracts for every summarization prompt pack.

The prompt files are data the pipeline depends on: the summarizer wraps a
style's `chunk` prompt around transcript segments, feeds `merge` a series of
`### Section N` blocks, feeds `validate` a `## Draft summary` plus
`## Section extracts`, and the notes assembler and truncation checker key off
specific headings in the output those prompts request. These tests pin each of
those contracts so a prompt edit cannot silently break the pipeline, and spot
check the voice and structure that make each style distinct.
"""

from types import SimpleNamespace

import pytest

from speaker_transcriber.models.notes_assembly import build_body
from speaker_transcriber.models.summarization import RequirementsSummarizer
from speaker_transcriber.prompts import (
    DEFAULT_STYLE,
    DOCUMENT_PIPELINE,
    MEETING_PIPELINE,
    PROMPT_FILENAMES,
    SEQUENTIAL_PIPELINE,
    SUMMARY_STYLES,
    get_prompt,
    get_style,
    load_prompts,
    style_ids,
)


STYLE_IDS = style_ids()
MEETING_STYLES = tuple(
    style.style_id for style in SUMMARY_STYLES if style.pipeline == MEETING_PIPELINE
)
DOCUMENT_STYLES = tuple(
    style.style_id for style in SUMMARY_STYLES if style.pipeline == DOCUMENT_PIPELINE
)
SEQUENTIAL_STYLES = tuple(
    style.style_id for style in SUMMARY_STYLES if style.pipeline == SEQUENTIAL_PIPELINE
)
MERGING_STYLES = MEETING_STYLES + DOCUMENT_STYLES

MORE_MARKER = "[MORE SEGMENTS FOLLOW]"
END_MARKER = "[END OF TRANSCRIPT]"
ACTION_TABLE_COLUMNS = "Owner | Action | Priority"

# Styles whose merge and format passes must produce the standard action table
# that the meeting-document parser and PDF exporter know how to render.
ACTION_TABLE_STYLES = MEETING_STYLES + (
    "standup_meeting",
    "technical_meeting",
    "internal_newsletter",
)


@pytest.fixture(scope="module", autouse=True)
def _loaded_prompts() -> None:
    load_prompts()


def prompt_text(name: str, style_id: str) -> str:
    """The prompt with hard line wraps collapsed, so assertions can match
    phrases that happen to span a wrapped line in the source file."""
    return " ".join(get_prompt(name, style_id).split())


def _bare_summarizer(num_ctx: int, style: str = DEFAULT_STYLE) -> RequirementsSummarizer:
    summarizer = RequirementsSummarizer.__new__(RequirementsSummarizer)
    summarizer.model_name = "test-model"
    summarizer.num_ctx = num_ctx
    summarizer.style = get_style(style)
    summarizer.cancel_event = None
    summarizer.client = None
    return summarizer


class _RecordingClient:
    def __init__(self, outputs: list[str] | None = None) -> None:
        self.outputs = list(outputs or [])
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        text = self.outputs.pop(0) if self.outputs else "ok"
        yield SimpleNamespace(response=text, thinking="")


# ---------------------------------------------------------------------------
# Universal guardrails: every style, every stage.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_system_states_a_priority_order_for_conflicting_rules(style_id: str) -> None:
    """Small models need to know what wins when rules collide."""
    system = prompt_text("system", style_id)
    assert "in this order" in system
    assert "never invent" in system.lower()


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_system_bans_truncation_meta_notes(style_id: str) -> None:
    """No style may ever claim the source was cut off."""
    system = prompt_text("system", style_id)
    assert "mid-sentence" in system
    assert "truncated" in system or "cut off" in system


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_system_bans_preambles_and_code_fences(style_id: str) -> None:
    """The output is the document itself, never wrapped or introduced."""
    system = prompt_text("system", style_id)
    assert "preamble" in system
    assert "code fence" in system


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_system_explains_both_continuation_markers(style_id: str) -> None:
    """The markers the code inserts must be spelled exactly as inserted."""
    system = prompt_text("system", style_id)
    assert MORE_MARKER in system
    assert END_MARKER in system
    assert "continuation" in system.lower()


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_chunk_starts_directly_and_never_echoes_markers(style_id: str) -> None:
    """Segment outputs are stitched together, so no wrapper text may leak in."""
    chunk = prompt_text("chunk", style_id)
    assert "Start directly" in chunk
    assert f"Do not echo the `{MORE_MARKER}`" in chunk
    assert END_MARKER in chunk


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_chunk_explains_the_running_background_when_the_style_uses_it(
    style_id: str,
) -> None:
    """Styles fed a running outline must be told not to restate it."""
    chunk = prompt_text("chunk", style_id)
    if get_style(style_id).uses_running_outline:
        assert "background" in chunk.lower()
        assert "only what is new" in chunk.lower()
    else:
        assert "background" not in chunk.lower()


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_merge_describes_its_numbered_section_input(style_id: str) -> None:
    """The summarizer packs sources as `### Section N`; the prompt must say so
    and must forbid copying that scaffolding into the output."""
    merge = prompt_text("merge", style_id)
    assert "`### Section" in merge
    assert "### Section N" in merge


@pytest.mark.parametrize("style_id", MERGING_STYLES)
def test_merge_handles_hierarchical_rounds_and_overlap(style_id: str) -> None:
    """Merge output can be re-merged in a later round, and consecutive
    extracts overlap, so both cases must be covered."""
    merge = prompt_text("merge", style_id)
    assert "earlier draft" in merge
    assert "once" in merge.lower()


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_validate_names_its_inputs_and_returns_the_document(style_id: str) -> None:
    """The validator sees the wrappers the code builds and must return the
    corrected document rather than a review."""
    validate = prompt_text("validate", style_id)
    assert "## Draft summary" in validate
    assert "## Section extracts" in validate
    assert "comment list" in validate
    assert "unchanged" in validate


@pytest.mark.parametrize("style_id", MERGING_STYLES)
def test_validate_knows_the_extracts_overlap(style_id: str) -> None:
    validate = prompt_text("validate", style_id)
    assert "overlap" in validate.lower()


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_validate_protects_correct_content(style_id: str) -> None:
    """Validation must never be allowed to shrink the record. Two styles are
    the exception, because deleting is their job: the pitch deck removes
    unsupported claims and the external newsletter removes internal leaks."""
    validate = prompt_text("validate", style_id)
    if style_id == "pitch_deck":
        assert "Delete anything that does not" in validate
    elif style_id == "external_newsletter":
        assert "remove anything internal" in validate
    else:
        assert "Never shorten" in validate


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_format_is_a_pure_formatting_pass(style_id: str) -> None:
    fmt = prompt_text("format", style_id)
    assert "formatting pass" in fmt
    assert "not a summarization pass" in fmt
    assert "no preamble" in fmt
    assert "code fence" in fmt


# ---------------------------------------------------------------------------
# Pipeline contracts: what each family's merge pass owns.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_merge_and_validate_promise_the_required_sections(style_id: str) -> None:
    """`_looks_truncated` treats near-cap output without these sections as cut
    off, so the merge and validate prompts must demand them."""
    style = get_style(style_id)
    merge = prompt_text("merge", style_id).lower()
    validate = prompt_text("validate", style_id).lower()
    for section in style.required_sections:
        assert section in merge, f"{style_id}/merge never asks for '{section}'"
        assert section in validate, f"{style_id}/validate never checks '{section}'"


@pytest.mark.parametrize("style_id", MEETING_STYLES)
def test_meeting_merges_write_front_matter_only(style_id: str) -> None:
    """Meeting styles append the detail notes mechanically; the merge pass must
    not regenerate them."""
    merge = prompt_text("merge", style_id)
    assert "front matter" in merge
    assert "appended automatically" in merge
    assert "detailed topic sections" in merge


@pytest.mark.parametrize("style_id", DOCUMENT_STYLES)
def test_document_merges_own_the_whole_document(style_id: str) -> None:
    """Document styles keep only the merge output, so it must be complete and
    must not drag the raw notes along."""
    merge = prompt_text("merge", style_id)
    assert "whole" in merge
    assert "Do not append" in merge


@pytest.mark.parametrize("style_id", SEQUENTIAL_STYLES)
def test_sequential_merges_are_stitching_passes(style_id: str) -> None:
    merge = prompt_text("merge", style_id)
    assert "stitching pass" in merge


@pytest.mark.parametrize("style_id", ACTION_TABLE_STYLES)
def test_action_tables_use_the_standard_columns(style_id: str) -> None:
    """The document parser and PDF exporter expect this exact pipe table."""
    assert ACTION_TABLE_COLUMNS in prompt_text("merge", style_id)
    assert ACTION_TABLE_COLUMNS in prompt_text("format", style_id)


@pytest.mark.parametrize("style_id", MEETING_STYLES)
def test_meeting_chunks_ban_generic_headings(style_id: str) -> None:
    """Generic headings are dropped by the assembler, taking their bullets'
    context with them, so the extraction pass must never write one."""
    chunk = prompt_text("chunk", style_id)
    assert "generic heading" in chunk
    for banned in ("Discussion", "Recap", "Continuation"):
        assert banned in chunk


@pytest.mark.parametrize("style_id", MEETING_STYLES)
def test_meeting_chunks_use_headings_the_assembler_can_merge(style_id: str) -> None:
    """The scaffold headings the chunk prompt requests must be ones the notes
    assembler recognizes, so repeats across segments collapse cleanly."""
    chunk = prompt_text("chunk", style_id)
    assert "`## Decisions`" in chunk
    assert "`## Action items`" in chunk
    assert "participants list" in chunk


def test_the_requested_scaffold_headings_survive_assembly() -> None:
    """Two segments using the exact headings the meeting chunk prompts request
    must collapse into single sections with no duplicate lines."""
    extracts = [
        "## Shader Failures\n- Cash: the packaged build fails on the shader step.\n\n"
        "## Decisions\n- Ship the fix on Friday.\n\n"
        "## Action items\n- Cash: clear the derived data cache (High).",
        "## Shader Failures\n- Cash: the packaged build fails on the shader step.\n\n"
        "## Action items\n- Cash: clear the derived data cache (High).\n"
        "- Andrew: test on the older driver.",
    ]
    body = build_body("", extracts)
    assert body.count("## Shader Failures") == 1
    assert body.count("the packaged build fails on the shader step") == 1
    assert body.count("clear the derived data cache") == 1
    assert "Additional Action Items" in body
    assert "test on the older driver" in body


# ---------------------------------------------------------------------------
# The prompts must match what the summarizer actually sends.
# ---------------------------------------------------------------------------


def test_merge_prompt_promise_matches_the_real_merge_payload() -> None:
    """The merge prompt tells the model to expect `### Section N` blocks; the
    summarizer must actually build them that way."""
    client = _RecordingClient(["ok"])
    summarizer = _bare_summarizer(8192)
    summarizer.client = client
    summarizer._merge(["notes about alpha", "notes about beta"])
    prompt = client.calls[0]["prompt"]
    assert prompt.startswith(get_prompt("merge", DEFAULT_STYLE))
    assert "### Section 1\n\nnotes about alpha" in prompt
    assert "### Section 2\n\nnotes about beta" in prompt


def test_validate_prompt_promise_matches_the_real_validate_payload() -> None:
    """The validate prompt names `## Draft summary` and `## Section extracts`;
    the summarizer must wrap its inputs with exactly those headings."""
    client = _RecordingClient(["x"])
    summarizer = _bare_summarizer(8192)
    summarizer.client = client
    summarizer._validate(
        "# Draft\n\ncontent",
        ["extract one", "extract two"],
        on_progress=None,
        on_chunk=None,
        on_section_break=None,
        on_reasoning=None,
        stage_start=0.8,
    )
    prompt = client.calls[0]["prompt"]
    assert prompt.startswith(get_prompt("validate", DEFAULT_STYLE))
    assert "## Draft summary\n\n# Draft" in prompt
    assert "## Section extracts" in prompt
    assert "### Extract 1\n\nextract one" in prompt


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_chunk_instruction_fits_the_extract_stage_budget(style_id: str) -> None:
    """The chunk instruction shares the extract-stage context with the
    transcript text and the running outline; it must fit in the slack."""
    summarizer = _bare_summarizer(8192)
    slack = (
        summarizer._prompt_char_budget("extract")
        - summarizer._chunk_char_limit()
        - summarizer._running_char_budget()
    )
    wrapper_allowance = 300  # section headers and markers added by _chunk_prompt
    chunk = prompt_text("chunk", style_id)
    assert len(chunk) + wrapper_allowance <= slack, (
        f"{style_id}/chunk.txt is {len(chunk)} characters and no longer fits "
        f"the extract-stage instruction slack of {slack}"
    )


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_prompts_stay_within_size_ceilings(style_id: str) -> None:
    """Every prompt rides along inside num_ctx on its stage; growth here is a
    silent tax on the transcript budget."""
    ceilings = {
        "system": 3000,
        "chunk": 3000,
        "merge": 3400,
        "validate": 2400,
        "format": 2600,
    }
    floors = 400
    for name in PROMPT_FILENAMES:
        text = get_prompt(name, style_id)
        assert len(text) <= ceilings[name], (
            f"{style_id}/{name}.txt is {len(text)} characters "
            f"(ceiling {ceilings[name]})"
        )
        assert len(text) >= floors, f"{style_id}/{name}.txt looks truncated"


@pytest.mark.parametrize("style_id", STYLE_IDS)
def test_prompts_contain_no_placeholders_or_tabs(style_id: str) -> None:
    for name in PROMPT_FILENAMES:
        text = get_prompt(name, style_id)
        assert "\t" not in text, f"{style_id}/{name}.txt contains a tab"
        for leftover in ("TODO", "FIXME", "XXX", "{", "}"):
            assert leftover not in text, (
                f"{style_id}/{name}.txt contains placeholder text '{leftover}'"
            )


@pytest.mark.parametrize("name", sorted(PROMPT_FILENAMES))
def test_every_style_has_a_distinct_prompt(name: str) -> None:
    """A copy-paste that leaves two styles identical would make the style
    picker cosmetic; every pack must differ at every stage."""
    texts = [get_prompt(name, style_id) for style_id in STYLE_IDS]
    assert len(set(texts)) == len(STYLE_IDS)


# ---------------------------------------------------------------------------
# Style-specific contracts: the voice and structure of each pack.
# ---------------------------------------------------------------------------


SPOT_CHECKS: dict[str, dict[str, tuple[str, ...]]] = {
    "meeting_summary": {
        "system": ("expert analyst", "speaker labels"),
        "chunk": ("## Packaged Build Failures", "`## Technical details`"),
        "merge": ("## Executive Summary", "## Closing Assessment"),
        "validate": ("front matter",),
        "format": ("## Closing Assessment", "Mitigation:"),
    },
    "art_meeting": {
        "system": ("art director", "adjectives"),
        "chunk": ("## Forest Biome Colour Keys", "`## Approvals`"),
        "merge": ("## Visual Direction", "## References"),
        "validate": ("approved",),
        "format": ("## Feedback and Approvals",),
    },
    "design_meeting": {
        "system": ("product designer", "dropped"),
        "chunk": ("## Onboarding Drop-Off", "`## Alternatives`"),
        "merge": ("## Alternatives Considered", "## What to Prototype Next"),
        "validate": ("prototype",),
        "format": ("## Problem Framing",),
    },
    "business_meeting": {
        "system": ("unit, period", "never round"),
        "chunk": ("## Q3 Pricing Change", "actual, forecast, or estimate"),
        "merge": ("## Numbers and Budget", "## Stakeholders"),
        "validate": ("Check the numbers first",),
        "format": ("## Goals and KPIs",),
    },
    "casual_meeting": {
        "system": ("warmer voice", "Warm does not mean vague"),
        "chunk": ("## The Launch Trailer", "`## Snags`"),
        "merge": ("## What We Decided", "contractions are fine"),
        "validate": ("warm readable voice",),
        "format": ("## Snags and Worries",),
    },
    "technical_meeting": {
        "system": ("decision record", "rejected"),
        "chunk": ("### Precompile shaders in CI", "`## Consequences`"),
        "merge": ("## Options Considered", "no decision was reached"),
        "validate": ("rejected",),
        "format": ("## Options Considered",),
    },
    "standup_meeting": {
        "system": ("status board", "under a minute"),
        "chunk": ("### Priya", "- Done:", "- Blocked:"),
        "merge": ("## Team Themes", "exactly once"),
        "validate": ("exactly once",),
        "format": ("- Doing:",),
    },
    "pitch_deck": {
        "system": ("slide language", "not said in the room is a lie"),
        "chunk": ("## Problem", "three days per asset"),
        "merge": ("logline", "## Ask"),
        "validate": ("Check accuracy first",),
        "format": ("logline",),
    },
    "internal_newsletter": {
        "system": ("candid", "Never spin"),
        "chunk": ("## What happened", "`## Shoutouts`"),
        "merge": ("## The Short Version", "## Who Owns What"),
        "validate": ("smoothed into consensus",),
        "format": ("## Still Open",),
    },
    "external_newsletter": {
        "system": ("quoted", "the team"),
        "chunk": ("## Not for publication", "outward-facing"),
        "merge": ("## Not for publication", "## What's Shipping"),
        "validate": ("Check safety first",),
        "format": ("## Highlights",),
    },
    "pure_transcription": {
        "system": ("transcript editor", "**Speaker:**", "disfluency"),
        "chunk": ("**Cash:**", "mid-sentence"),
        "merge": ("stitching pass",),
        "validate": ("paraphrased",),
        "format": ("**Speaker:**",),
    },
    "ai_voiced_dialogue": {
        "system": ("Host A", "Host B", "four million dollars"),
        "chunk": ("**Host A:**", "pick up mid-conversation"),
        "merge": ("alternate",),
        "validate": ("**Host B:**",),
        "format": ("read aloud",),
    },
}


def test_spot_checks_cover_every_style() -> None:
    assert set(SPOT_CHECKS) == set(STYLE_IDS)


@pytest.mark.parametrize(
    ("style_id", "name"),
    [
        (style_id, name)
        for style_id, checks in sorted(SPOT_CHECKS.items())
        for name in sorted(checks)
    ],
)
def test_each_style_keeps_its_own_voice_and_structure(
    style_id: str, name: str
) -> None:
    text = prompt_text(name, style_id)
    for expected in SPOT_CHECKS[style_id][name]:
        assert expected in text, (
            f"{style_id}/{name}.txt no longer mentions '{expected}'"
        )


# ---------------------------------------------------------------------------
# Family-wide bans that keep known failure modes from returning.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("style_id", MEETING_STYLES)
def test_meeting_chunks_forbid_filler_lines(style_id: str) -> None:
    """'None recorded' placeholder lines were a chronic small-model failure."""
    chunk = prompt_text("chunk", style_id)
    assert "filler line" in chunk
    assert "Omit any heading" in chunk


@pytest.mark.parametrize("style_id", SEQUENTIAL_STYLES)
def test_sequential_chunks_forbid_titles_and_summaries(style_id: str) -> None:
    """Sequential outputs are concatenated verbatim, so any per-segment
    scaffolding would appear repeatedly in the final document."""
    chunk = prompt_text("chunk", style_id).lower()
    assert "no title" in chunk or "do not write a title" in chunk
    assert "summar" in chunk  # no summary / never summarize


def test_transcription_never_invents_sentence_endings() -> None:
    """Segments are cut mechanically; completing a cut-off sentence would be
    pure invention."""
    chunk = prompt_text("chunk", "pure_transcription")
    assert "never invent words to complete a cut-off sentence" in chunk


def test_dialogue_prompts_write_figures_for_the_ear() -> None:
    """A TTS voice reads '$4M' badly; every dialogue stage must require
    spoken-word figures."""
    for name in ("system", "chunk", "format"):
        text = prompt_text(name, "ai_voiced_dialogue")
        assert "$4M" in text, f"ai_voiced_dialogue/{name}.txt lost the TTS figure rule"
