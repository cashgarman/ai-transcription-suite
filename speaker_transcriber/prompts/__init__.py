"""Summarization prompt packs, one per summary style.

Every style owns a full pack (`system`, `chunk`, `merge`, `validate`, `format`)
so that both the per-segment extraction pass and the final document match the
style the user asked for. Only `continue.txt` is shared: finishing a truncated
generation is the same job no matter what is being written.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


LOGGER = logging.getLogger("speaker_transcriber.prompts")

PROMPT_FILENAMES = {
    "system": "system.txt",
    "chunk": "chunk.txt",
    "merge": "merge.txt",
    "validate": "validate.txt",
    "format": "format.txt",
}

SHARED_PROMPT_FILENAMES = {
    "continue": "continue.txt",
}

# How the summarizer drives a style through the chunk/merge/validate loop.
MEETING_PIPELINE = "meeting"
"""Segment notes, then an overview merged in front of them."""

DOCUMENT_PIPELINE = "document"
"""Segment notes merged into one document; the notes are not appended."""

SEQUENTIAL_PIPELINE = "sequential"
"""Segment output concatenated in order, with no merge pass at all."""


SEGMENT_NOTES_SECTION_ID = "detailed_notes"
"""Well-known id for the per-topic notes body a meeting document appends.

Unlike heading-owned sections, the body is a run of arbitrary topic headings,
so excluding it is handled structurally (the assembly step is skipped) rather
than by heading matching.
"""


@dataclass(frozen=True)
class SummarySection:
    """One user-toggleable section of a style's finished document.

    ``headings`` lists every heading the section's content can appear under in
    the final Markdown: first the heading the merge prompt asks for, then any
    alias the deterministic notes assembly can emit for the same content
    (matching is case-insensitive). The one heading-less section is
    ``detailed_notes``, whose removal is structural. Sections a style treats
    as its core — a stand-up's Updates, a pitch's Problem and Solution — are
    simply not registered, so they can never be turned off.
    """

    section_id: str
    label: str
    description: str
    headings: tuple[str, ...]
    default_included: bool = True


@dataclass(frozen=True)
class SummaryStyle:
    style_id: str
    display_name: str
    description: str
    pipeline: str = MEETING_PIPELINE
    required_sections: tuple[str, ...] = ()
    uses_running_outline: bool = True
    """Whether a segment is told what earlier segments already covered."""
    sections: tuple[SummarySection, ...] = ()
    """The optional sections a user may include or exclude for this style."""
    trailing_sections: tuple[str, ...] = ()
    """Headings moved to the very end of the assembled document."""

    @property
    def is_meeting_family(self) -> bool:
        return self.pipeline == MEETING_PIPELINE

    @property
    def keeps_segment_notes(self) -> bool:
        return self.pipeline in (MEETING_PIPELINE, SEQUENTIAL_PIPELINE)

    def requires_action_table(self, excluded_section_ids: Iterable[str] = ()) -> bool:
        """Whether a formatted document must still carry the action table."""
        return "action_items" not in set(excluded_section_ids or ())


_MEETING_SECTIONS = ("action items", "open questions")

_EXECUTIVE_SUMMARY = SummarySection(
    "executive_summary",
    "Executive summary",
    "A few paragraphs covering the arc of the whole discussion.",
    ("Executive Summary",),
)
_KEY_DECISIONS = SummarySection(
    "decisions",
    "Key decisions",
    "Numbered list of every decision reached, with the reasoning.",
    ("Key Decisions and Direction", "Additional Decisions"),
)
_ACTION_ITEMS = SummarySection(
    "action_items",
    "Action items",
    "Owner / Action / Priority table of every action item.",
    ("Action Items", "Additional Action Items"),
)
_OPEN_QUESTIONS = SummarySection(
    "open_questions",
    "Open questions",
    "Questions raised that were not resolved.",
    ("Open Questions", "Additional Open Questions"),
)
_RISKS = SummarySection(
    "risks",
    "Risks and blockers",
    "Risks, dependencies, and blockers, with mitigations when discussed.",
    ("Risks, Dependencies, and Blockers", "Additional Risks and Blockers"),
)
_CLOSING_ASSESSMENT = SummarySection(
    "closing_assessment",
    "Closing assessment",
    "Short closing remarks on where things stand, at the document's end.",
    ("Closing Assessment",),
)
_DETAILED_NOTES = SummarySection(
    SEGMENT_NOTES_SECTION_ID,
    "Detailed discussion notes",
    "The full per-topic dialogue notes, after the overview sections.",
    (),
)

_MEETING_TRAILING = ("Closing Assessment",)

SUMMARY_STYLES: tuple[SummaryStyle, ...] = (
    SummaryStyle(
        "pure_transcription",
        "Pure Transcription",
        "Readable cleaned-up transcript, no summarizing.",
        pipeline=SEQUENTIAL_PIPELINE,
        uses_running_outline=False,
    ),
    SummaryStyle(
        "meeting_summary",
        "Meeting Summary",
        "Full meeting document: overview, decisions, actions, detailed notes.",
        required_sections=_MEETING_SECTIONS,
        sections=(
            _EXECUTIVE_SUMMARY,
            _KEY_DECISIONS,
            _ACTION_ITEMS,
            _OPEN_QUESTIONS,
            _RISKS,
            _DETAILED_NOTES,
            _CLOSING_ASSESSMENT,
        ),
        trailing_sections=_MEETING_TRAILING,
    ),
    SummaryStyle(
        "pitch_deck",
        "Pitch Deck",
        "Slide-ready outline: problem, solution, proof, ask.",
        pipeline=DOCUMENT_PIPELINE,
        sections=(
            SummarySection(
                "insight",
                "Insight",
                "Why this is possible or urgent now.",
                ("Insight",),
            ),
            SummarySection(
                "proof",
                "Proof",
                "Traction, tests, and evidence actually stated.",
                ("Proof",),
            ),
            SummarySection(
                "market",
                "Market and competition",
                "Audience, segments, alternatives, and competitors named.",
                ("Market and Competition",),
            ),
            SummarySection(
                "business_model",
                "Business model",
                "Pricing, model, cost, funding, and resourcing.",
                ("Business Model",),
            ),
            SummarySection(
                "ask",
                "Ask",
                "The specific request, and what happens next.",
                ("Ask",),
            ),
            SummarySection(
                "risks_objections",
                "Risks and objections",
                "Pushback raised in the room, with the answers given.",
                ("Risks and Objections",),
            ),
        ),
    ),
    SummaryStyle(
        "internal_newsletter",
        "Internal Newsletter",
        "Candid team update with owners and shoutouts.",
        pipeline=DOCUMENT_PIPELINE,
        sections=(
            SummarySection(
                "short_version",
                "The short version",
                "Two or three sentences a busy reader can stop after.",
                ("The Short Version",),
            ),
            SummarySection(
                "decisions",
                "Decisions",
                "Every decision, with who made it and why.",
                ("Decisions",),
            ),
            SummarySection(
                "owners",
                "Who owns what",
                "Owner / Action / Priority table of assigned work.",
                ("Who Owns What",),
            ),
            SummarySection(
                "still_open",
                "Still open",
                "Unsettled arguments, blocked work, and open questions.",
                ("Still Open",),
            ),
            SummarySection(
                "whats_next",
                "What's next",
                "What happens between now and the next update.",
                ("What's Next",),
            ),
            SummarySection(
                "shoutouts",
                "Shoutouts",
                "Praise actually given, and who it was for.",
                ("Shoutouts",),
            ),
        ),
    ),
    SummaryStyle(
        "external_newsletter",
        "External Newsletter",
        "Polished customer-facing update with no internals.",
        pipeline=DOCUMENT_PIPELINE,
        sections=(
            SummarySection(
                "in_this_issue",
                "In this issue",
                "A short lede that frames the issue.",
                ("In This Issue",),
            ),
            SummarySection(
                "whats_shipping",
                "What's shipping",
                "What is live or arriving, with committed dates.",
                ("What's Shipping",),
            ),
            SummarySection(
                "whats_next",
                "What's next",
                "Direction and next steps that are safe to share.",
                ("What's Next",),
            ),
            SummarySection(
                "thank_you",
                "Thank you",
                "A brief closing line to the audience.",
                ("Thank You",),
            ),
        ),
    ),
    SummaryStyle(
        "technical_meeting",
        "Technical Meeting",
        "Decision record: problem, options, decision, consequences.",
        pipeline=DOCUMENT_PIPELINE,
        required_sections=("decision",),
        sections=(
            SummarySection(
                "context",
                "Context",
                "The system and situation being discussed.",
                ("Context",),
            ),
            SummarySection(
                "options",
                "Options considered",
                "Each option floated, with tradeoffs and who argued them.",
                ("Options Considered",),
            ),
            SummarySection(
                "consequences",
                "Consequences",
                "What the decision commits the team to.",
                ("Consequences",),
            ),
            _OPEN_QUESTIONS,
            SummarySection(
                "technical_details",
                "Technical details",
                "Versions, file names, paths, measurements, and deadlines.",
                ("Technical Details",),
            ),
            SummarySection(
                "follow_ups",
                "Follow-ups",
                "Owner / Action / Priority table of assigned work.",
                ("Follow-ups",),
            ),
        ),
    ),
    SummaryStyle(
        "art_meeting",
        "Art Meeting",
        "Meeting notes focused on visual direction and asset feedback.",
        required_sections=_MEETING_SECTIONS,
        sections=(
            _EXECUTIVE_SUMMARY,
            SummarySection(
                "visual_direction",
                "Visual direction",
                "Where the look landed: mood, palette, lighting, and the "
                "adjectives used.",
                ("Visual Direction",),
            ),
            SummarySection(
                "references",
                "References",
                "Every artist, film, game, image, or link cited.",
                ("References",),
            ),
            SummarySection(
                "assets",
                "Assets, characters, and shots",
                "Each piece discussed, with its current state.",
                ("Assets, Characters, and Shots",),
            ),
            SummarySection(
                "feedback_approvals",
                "Feedback and approvals",
                "What was asked for, approved, or rejected, piece by piece.",
                ("Feedback and Approvals",),
            ),
            _KEY_DECISIONS,
            _ACTION_ITEMS,
            _OPEN_QUESTIONS,
            _RISKS,
            _DETAILED_NOTES,
            _CLOSING_ASSESSMENT,
        ),
        trailing_sections=_MEETING_TRAILING,
    ),
    SummaryStyle(
        "design_meeting",
        "Design Meeting",
        "Meeting notes focused on problem framing and what to prototype.",
        required_sections=_MEETING_SECTIONS,
        sections=(
            _EXECUTIVE_SUMMARY,
            SummarySection(
                "problem_framing",
                "Problem framing",
                "What problem is being solved, for whom, and the evidence.",
                ("Problem Framing",),
            ),
            SummarySection(
                "constraints",
                "Constraints",
                "Technical, platform, time, budget, brand, and accessibility "
                "limits.",
                ("Constraints",),
            ),
            SummarySection(
                "alternatives",
                "Alternatives considered",
                "Each option floated, with the arguments for and against.",
                ("Alternatives Considered",),
            ),
            SummarySection(
                "prototype_next",
                "What to prototype next",
                "What the team intends to try, test, or mock up.",
                ("What to Prototype Next",),
            ),
            _KEY_DECISIONS,
            _ACTION_ITEMS,
            _OPEN_QUESTIONS,
            _RISKS,
            _DETAILED_NOTES,
            _CLOSING_ASSESSMENT,
        ),
        trailing_sections=_MEETING_TRAILING,
    ),
    SummaryStyle(
        "business_meeting",
        "Business Meeting",
        "Meeting notes focused on goals, numbers, and commercial decisions.",
        required_sections=_MEETING_SECTIONS,
        sections=(
            _EXECUTIVE_SUMMARY,
            SummarySection(
                "goals_kpis",
                "Goals and KPIs",
                "Each objective with the measure and target attached to it.",
                ("Goals and KPIs",),
            ),
            SummarySection(
                "numbers_budget",
                "Numbers and budget",
                "Every figure with its unit, period, and status.",
                ("Numbers and Budget",),
            ),
            SummarySection(
                "stakeholders",
                "Stakeholders",
                "Each person, team, partner, or customer, and what they want.",
                ("Stakeholders",),
            ),
            SummarySection(
                "timeline",
                "Timeline and milestones",
                "Dates in order, with what depends on each one.",
                ("Timeline and Milestones",),
            ),
            _KEY_DECISIONS,
            _ACTION_ITEMS,
            _OPEN_QUESTIONS,
            _RISKS,
            _DETAILED_NOTES,
            _CLOSING_ASSESSMENT,
        ),
        trailing_sections=_MEETING_TRAILING,
    ),
    SummaryStyle(
        "casual_meeting",
        "Casual Meeting",
        "The same facts as a meeting summary, told as a warm recap.",
        required_sections=_MEETING_SECTIONS,
        sections=(
            _EXECUTIVE_SUMMARY,
            SummarySection(
                "decisions",
                "What we decided",
                "Numbered list of every decision, with the reason behind it.",
                ("What We Decided", "Additional Decisions"),
            ),
            _ACTION_ITEMS,
            _OPEN_QUESTIONS,
            SummarySection(
                "risks",
                "Snags and worries",
                "What is stuck or worrying, and what was said about it.",
                ("Snags and Worries", "Additional Risks and Blockers"),
            ),
            _DETAILED_NOTES,
            _CLOSING_ASSESSMENT,
        ),
        trailing_sections=_MEETING_TRAILING,
    ),
    SummaryStyle(
        "standup_meeting",
        "Stand-Up Meeting",
        "Per-person yesterday/today/blockers plus team themes.",
        pipeline=DOCUMENT_PIPELINE,
        sections=(
            SummarySection(
                "team_themes",
                "Team themes",
                "Patterns across the updates: what most of the team is on.",
                ("Team Themes",),
            ),
            SummarySection(
                "blockers",
                "Blockers table",
                "Owner / Action / Priority table of blockers needing action.",
                ("Blockers",),
            ),
            SummarySection(
                "announcements",
                "Announcements",
                "Things said to the whole team.",
                ("Announcements",),
            ),
            SummarySection(
                "shoutouts",
                "Shoutouts",
                "Praise actually given, and who it was for.",
                ("Shoutouts",),
            ),
        ),
    ),
    SummaryStyle(
        "ai_voiced_dialogue",
        "AI Voiced Dialogue",
        "Two-host recap script written to be read aloud.",
        pipeline=SEQUENTIAL_PIPELINE,
    ),
)

DEFAULT_STYLE = "meeting_summary"

_STYLES_BY_ID = {style.style_id: style for style in SUMMARY_STYLES}

_cache: dict[str, str] = {}


def style_ids() -> tuple[str, ...]:
    return tuple(style.style_id for style in SUMMARY_STYLES)


def is_known_style(style_id: str | None) -> bool:
    return str(style_id or "") in _STYLES_BY_ID


def normalize_style(style_id: str | None) -> str:
    name = str(style_id or "").strip()
    return name if name in _STYLES_BY_ID else DEFAULT_STYLE


def get_style(style_id: str | None) -> SummaryStyle:
    return _STYLES_BY_ID[normalize_style(style_id)]


def style_display_name(style_id: str | None) -> str:
    return get_style(style_id).display_name


def style_sections(style_id: str | None = None) -> tuple[SummarySection, ...]:
    """The user-toggleable sections of a style, in document order."""
    return get_style(style_id).sections


def normalize_excluded_sections(
    style_id: str | None,
    excluded_ids: Iterable[str],
) -> tuple[str, ...]:
    """The subset of ``excluded_ids`` the style knows, in registry order."""
    excluded = {str(item) for item in excluded_ids or ()}
    return tuple(
        section.section_id
        for section in style_sections(style_id)
        if section.section_id in excluded
    )


def excluded_section_headings(
    style_id: str | None,
    excluded_ids: Iterable[str],
) -> tuple[str, ...]:
    """Every document heading owned by the excluded sections of a style."""
    excluded = set(normalize_excluded_sections(style_id, excluded_ids))
    headings: list[str] = []
    for section in style_sections(style_id):
        if section.section_id in excluded:
            headings.extend(section.headings)
    return tuple(headings)


def _looks_like_prompts_dir(candidate: Path) -> bool:
    if not (candidate / SHARED_PROMPT_FILENAMES["continue"]).is_file():
        return False
    return (candidate / "styles" / DEFAULT_STYLE / "system.txt").is_file()


def prompts_dir() -> Path:
    package_dir = Path(__file__).resolve().parent
    if _looks_like_prompts_dir(package_dir):
        return package_dir

    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    if getattr(sys, "frozen", False):
        install_dir = Path(sys.executable).resolve().parent
        roots.extend((install_dir / "_internal", install_dir))

    for root in roots:
        candidate = root / "speaker_transcriber" / "prompts"
        if _looks_like_prompts_dir(candidate):
            return candidate
    return package_dir


def style_dir(style_id: str | None = None) -> Path:
    return prompts_dir() / "styles" / normalize_style(style_id)


def cache_key(name: str, style_id: str | None = None) -> str:
    if name in SHARED_PROMPT_FILENAMES:
        return name
    return f"{normalize_style(style_id)}/{name}"


def _read_prompt(path: Path, missing: list[str]) -> str | None:
    if not path.is_file():
        missing.append(str(path))
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        missing.append(f"{path} (empty)")
        return None
    return text


def load_prompts() -> dict[str, str]:
    """Load every style pack plus the shared prompts, keyed ``style/name``."""
    directory = prompts_dir()
    loaded: dict[str, str] = {}
    missing: list[str] = []

    for key, filename in SHARED_PROMPT_FILENAMES.items():
        text = _read_prompt(directory / filename, missing)
        if text is not None:
            loaded[key] = text

    for style in SUMMARY_STYLES:
        pack_dir = directory / "styles" / style.style_id
        for name, filename in PROMPT_FILENAMES.items():
            text = _read_prompt(pack_dir / filename, missing)
            if text is not None:
                loaded[cache_key(name, style.style_id)] = text

    if missing:
        raise FileNotFoundError(
            "Missing or empty summarization prompt file(s):\n" + "\n".join(missing)
        )
    _cache.clear()
    _cache.update(loaded)
    LOGGER.info(
        "Loaded %d prompt(s) for %d style(s) from %s",
        len(loaded),
        len(SUMMARY_STYLES),
        directory,
    )
    return dict(_cache)


def reload_prompts() -> dict[str, str]:
    return load_prompts()


def get_prompt(name: str, style_id: str | None = None) -> str:
    key = cache_key(name, style_id)
    if key not in _cache:
        load_prompts()
    try:
        return _cache[key]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt '{key}'") from exc
