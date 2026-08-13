"""Assemble per-segment extracts into one topic-organized body of notes.

The summarizer keeps chunk extracts verbatim so that no meeting detail is lost,
but a model writing notes for segment seven cannot see what segment three
already said, so it restates it and re-emits the same scaffolding headings every
time. Everything in this module is deterministic clean-up of that overlap: drop
the per-segment scaffolding, merge blocks that describe the same topic, and drop
lines that repeat a point an earlier line (or the overview) already made.

De-duplication only ever removes a line that another line already covers. A
block is dropped when nothing unique is left in it, or when its own heading says
it is a recap; a recap-heavy block that still carries new material keeps that
material rather than being discarded wholesale, because losing detail is worse
than an extra bullet.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field


NEAR_DUPLICATE_RATIO = 0.8
COVERAGE_RATIO = 0.85
MIN_FUZZY_TOKENS = 5
MIN_COVERAGE_TOKENS = 5
MIN_TOKEN_LENGTH = 3
RARE_TOKEN_PROBES = 3
MIN_PREFIX_WORDS = 3
PLACEHOLDER_MAX_CHARS = 100

DISCUSSION_TITLE = "Discussion Notes"
TECHNICAL_TITLE = "Technical Details"

LEAD = "lead"
TOPIC = "topic"
CATEGORY = "category"
TECHNICAL = "technical"
GENERIC = "generic"
PARTICIPANTS = "participants"
RECAP = "recap"

_SECTION_RANK = {LEAD: 0, TOPIC: 0, TECHNICAL: 1, CATEGORY: 2}

_HEADING = re.compile(r"^\s*(?:[-*+\u2022]\s+)?#{1,6}\s+(.*?)\s*#*\s*$")
_BOLD_LABEL = re.compile(r"^(?:\*\*|__)(.+?)(?:\*\*|__)\s*:?\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+\u2022]|\d+[.)])\s+")
_EMPHASIS = re.compile(r"\*\*|__|[*_`]")
_TIMESTAMP = re.compile(r"\[?\b\d{1,2}:\d{2}(?::\d{2})?\b\s*(?:[-\u2013]\s*)?\]?")
_WORD = re.compile(r"[a-z0-9]+")
_RULE_LINE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,}|\\+)\s*$")
_MARKER = re.compile(r"\[?\b(?:MORE SEGMENTS FOLLOW|END OF TRANSCRIPT)\b\]?", re.IGNORECASE)
_BLANK_RUN = re.compile(r"\n{3,}")
_VARIANT_SUFFIX = re.compile(
    r"[\s\u2013\u2014-]*[(\[]?\s*\b(?:recap|cont|cont\.|continued|continuation|"
    r"part\s*\d+(?:\s*of\s*\d+)?|segment\s*\d+)\s*[)\]]?\s*$",
    re.IGNORECASE,
)
_CONTINUATION_PREFIX = re.compile(
    r"^(?:continued|continuation)(?:\s+(?:brief|notes|discussion|of))?\s*[:\u2013\u2014-]?\s+",
    re.IGNORECASE,
)
_TRAILING_PARENTHETICAL = re.compile(r"\s*[(\[][^)\]]*[)\]]\s*$")
_WRAPPED_TITLE = re.compile(r"^[(\[](.+)[)\]]$")
_VARIANT_PARENTHETICAL = re.compile(
    r"\s*[(\[][^)\]]*\b(?:recap|cont|cont\.|continued|continuation|part\s*\d+|"
    r"segment\s*\d+)\b[^)\]]*[)\]]\s*$",
    re.IGNORECASE,
)
_TRAILING_NOISE = re.compile(
    r"^\(?\s*(?:notes?\s+continue|continued\s+in|to\s+be\s+continued|"
    r"end\s+of\s+(?:segment|extract))",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(
    r"^(?:none|no|nothing|not)\b"
    r"(?=.*(?:record|stat|rais|mention|note|discuss|identif|explicit|segment|"
    r"applicable|available|assign|specifi))",
    re.IGNORECASE,
)
_EMPTY_MARKERS = frozenset(
    {"none", "n/a", "na", "nil", "not applicable", "none identified", "none noted"}
)
_STOPWORDS = frozenset(
    """
    a about all also an and any are as at be been being but by can could did do
    does for from had has have how in into is it its more most not of on one or
    other our out over should so some such than that the their them then there
    these they this those to too very was way were what when where which who
    will with would you your
    """.split()
)

_TITLE_FILLER = frozenset({"a", "an", "and", "for", "in", "of", "or", "the", "this", "to", "amp"})

# A heading is scaffolding only when every word in it belongs to that label. That
# keeps a real topic such as "Project Status and Technical Details" a topic
# instead of collapsing it into the Technical Details bucket.
_LABEL_RULES: tuple[tuple[frozenset[str], frozenset[str], str, str], ...] = (
    (
        frozenset({"participant", "participants", "attendee", "attendees", "speakers"}),
        frozenset(
            {
                "participant",
                "participants",
                "attendee",
                "attendees",
                "speaker",
                "speakers",
                "people",
                "present",
                "labels",
            }
        ),
        PARTICIPANTS,
        "",
    ),
    (
        frozenset({"recap", "recapitulation", "previously", "previous", "prior", "earlier"}),
        frozenset(
            {
                "recap",
                "recapitulation",
                "previously",
                "previous",
                "prior",
                "earlier",
                "discussed",
                "discussion",
                "discussions",
                "summary",
                "notes",
                "context",
                "segment",
                "segments",
            }
        ),
        RECAP,
        "",
    ),
    (
        frozenset(
            {
                "discussion",
                "discussions",
                "notes",
                "note",
                "summary",
                "overview",
                "topic",
                "topics",
                "points",
                "segment",
                "extract",
                "continuation",
                "continued",
            }
        ),
        frozenset(
            {
                "brief",
                "continuation",
                "continued",
                "context",
                "discussed",
                "discussion",
                "discussions",
                "extract",
                "general",
                "highlights",
                "key",
                "main",
                "meeting",
                "note",
                "notes",
                "overview",
                "point",
                "points",
                "segment",
                "summary",
                "topic",
                "topics",
            }
        ),
        GENERIC,
        "",
    ),
    (
        frozenset({"decision", "decisions"}),
        frozenset(
            {
                "decision",
                "decisions",
                "direction",
                "explicit",
                "key",
                "made",
                "reached",
                "taken",
            }
        ),
        CATEGORY,
        "Additional Decisions",
    ),
    (
        frozenset({"action", "actions", "steps", "todo", "todos"}),
        frozenset(
            {
                "action",
                "actions",
                "item",
                "items",
                "next",
                "owner",
                "owners",
                "steps",
                "todo",
                "todos",
            }
        ),
        CATEGORY,
        "Additional Action Items",
    ),
    (
        frozenset({"question", "questions", "thread", "threads"}),
        frozenset(
            {
                "answer",
                "answered",
                "answers",
                "asked",
                "open",
                "question",
                "questions",
                "raised",
                "thread",
                "threads",
                "unanswered",
            }
        ),
        CATEGORY,
        "Additional Open Questions",
    ),
    (
        frozenset({"risk", "risks", "blocker", "blockers", "dependency", "dependencies"}),
        frozenset(
            {
                "blocker",
                "blockers",
                "concern",
                "concerns",
                "dependencies",
                "dependency",
                "issue",
                "issues",
                "mitigation",
                "mitigations",
                "risk",
                "risks",
            }
        ),
        CATEGORY,
        "Additional Risks and Blockers",
    ),
    (
        frozenset({"technical"}),
        frozenset(
            {
                "detail",
                "details",
                "note",
                "notes",
                "status",
                "technical",
                "update",
                "updates",
            }
        ),
        TECHNICAL,
        TECHNICAL_TITLE,
    ),
)


@dataclass
class _Block:
    """One titled run of note lines, as written in an extract."""

    title: str
    key: str
    kind: str
    lines: list[str] = field(default_factory=list)


def assemble_notes(front_matter: str, extracts: Sequence[str]) -> str:
    """Join the generated overview with one merged, de-duplicated body of notes."""
    body = build_body(front_matter, extracts)
    parts = [front_matter.strip(), body]
    return "\n\n".join(part for part in parts if part).strip()


def build_body(front_matter: str, extracts: Sequence[str]) -> str:
    """Merge every extract into topic sections that each appear exactly once."""
    covered = _CoverageIndex(front_matter)
    seen = _LineIndex()
    merged: dict[str, _Block] = {}
    order: list[str] = []
    for extract in extracts:
        for block in _blocks_from_extract(extract):
            kept = _fresh_lines(block, seen, covered)
            if not kept:
                continue
            key = block.key
            if key not in merged and block.kind == TOPIC:
                key = _matching_key(key, order) or key
            existing = merged.get(key)
            if existing is None:
                merged[key] = _Block(block.title, key, block.kind, kept)
                order.append(key)
                continue
            if not _joins_cleanly(existing.lines[-1], kept[0]):
                existing.lines.append("")
            existing.lines.extend(kept)
    return _render([merged[key] for key in order])


def topic_titles(extracts: Sequence[str]) -> list[str]:
    """The topic headings recorded so far, in first-appearance order."""
    titles: list[str] = []
    seen: set[str] = set()
    for extract in extracts:
        for block in _blocks_from_extract(extract):
            if block.kind != TOPIC or block.key in seen:
                continue
            seen.add(block.key)
            titles.append(block.title)
    return titles


def fit_titles(titles: Sequence[str], budget: int) -> str:
    """A semicolon list of titles that fits the budget, oldest ones dropped first."""
    kept = list(titles)
    while kept:
        prefix = "" if len(kept) == len(titles) else "…; "
        joined = prefix + "; ".join(kept)
        if len(joined) <= budget or len(kept) == 1:
            return joined
        kept.pop(0)
    return ""


def recent_lines(extract: str, budget: int) -> str:
    """The tail of an extract, so the next segment knows where the notes stopped."""
    if budget <= 0:
        return ""
    lines: list[str] = []
    for block in _blocks_from_extract(extract):
        if block.kind in (PARTICIPANTS, RECAP):
            continue
        content = _trim_blank_edges(block.lines)
        if not content:
            continue
        lines.append(f"## {block.title}")
        lines.extend(content)
    kept: list[str] = []
    used = 0
    for line in reversed(lines):
        used += len(line) + 1
        if used > budget and kept:
            break
        kept.insert(0, line)
        if used > budget:
            break
    return "\n".join(_trim_blank_edges(kept))


def _is_wrapped_continuation(line: str) -> bool:
    return bool(line[:1].isspace()) and _BULLET.match(line) is None


def _joins_cleanly(last: str, first: str) -> bool:
    """True when two runs of notes can sit next to each other without a blank line."""
    return bool(_BULLET.match(last)) and bool(_BULLET.match(first))


def _render(blocks: Sequence[_Block]) -> str:
    ordered = sorted(blocks, key=lambda block: _SECTION_RANK.get(block.kind, 0))
    sections: list[str] = []
    for block in ordered:
        lines = _trim_blank_edges(block.lines)
        if not lines:
            continue
        sections.append(f"## {block.title}\n\n" + "\n".join(lines))
    return _BLANK_RUN.sub("\n\n", "\n\n".join(sections)).strip()


def _fresh_lines(block: _Block, seen: _LineIndex, covered: _CoverageIndex) -> list[str]:
    """The lines of a block that say something not already said."""
    if block.kind in (PARTICIPANTS, RECAP):
        return []
    kept: list[str] = []
    dropped_previous = False
    for line in block.lines:
        if not line.strip():
            kept.append("")
            continue
        if _is_wrapped_continuation(line):
            # A soft-wrapped bullet shares the fate of the line it belongs to,
            # so removing a repeat cannot leave half a sentence behind.
            if not dropped_previous:
                kept.append(line)
            continue
        dropped_previous = (block.kind == CATEGORY and covered.covers(line)) or seen.has(line)
        if dropped_previous:
            continue
        kept.append(line)
    if not any(line.strip() for line in kept):
        return []
    for line in kept:
        seen.add(line)
    return _trim_blank_edges(kept)


def _blocks_from_extract(extract: str) -> list[_Block]:
    """Split one extract into blocks, dropping per-segment scaffolding headings."""
    blocks: list[_Block] = []
    active: _Block | None = None
    generic: _Block | None = None
    for line in _clean_extract(extract).splitlines():
        heading = _heading_of(line)
        if heading is None:
            target = active or generic
            if target is None:
                generic = _Block(DISCUSSION_TITLE, DISCUSSION_TITLE, LEAD)
                blocks.append(generic)
                target = generic
            target.lines.append(line)
            continue
        kind, title = _classify(heading)
        if kind == GENERIC:
            # A scaffolding heading such as "Discussion" adds no topic of its own:
            # its lines belong to whatever topic is open, or to the lead-in notes.
            continue
        block = _Block(title or heading, _merge_key(title or heading), kind)
        blocks.append(block)
        active = block
    return blocks


def _heading_of(line: str) -> str | None:
    """The heading text of a line, for Markdown headings and bold label lines."""
    match = _HEADING.match(line)
    if match is not None:
        return match.group(1).strip()
    if line[:1].isspace():
        return None
    match = _BOLD_LABEL.match(line.strip())
    if match is not None:
        return match.group(1).strip().rstrip(":").strip()
    return None


def _classify(heading: str) -> tuple[str, str]:
    """The kind of section a heading introduces, and the title to print for it."""
    key = _normalize_title(heading)
    if not key:
        return (GENERIC, "")
    words = set(re.findall(r"[a-z]+", key)) - _TITLE_FILLER
    for core, allowed, kind, title in _LABEL_RULES:
        if words and words <= allowed and words & core:
            return (kind, title)
    return (TOPIC, _display_title(heading))


def _normalize_title(heading: str) -> str:
    """A merge key: same topic written a slightly different way lands on one key."""
    text = _base_title(heading).replace("&", " and ")
    text = _TRAILING_PARENTHETICAL.sub("", text)
    text = _VARIANT_SUFFIX.sub("", text)
    text = re.sub(r"[^\w\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _display_title(heading: str) -> str:
    """The topic as the notes wrote it, minus any recap or continuation marker."""
    text = _VARIANT_PARENTHETICAL.sub("", _base_title(heading))
    text = _VARIANT_SUFFIX.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" :").strip() or DISCUSSION_TITLE


def _base_title(heading: str) -> str:
    text = _EMPHASIS.sub("", heading).strip().strip("#").strip()
    text = _CONTINUATION_PREFIX.sub("", text).strip()
    wrapped = _WRAPPED_TITLE.match(text)
    return wrapped.group(1).strip() if wrapped is not None else text


def _merge_key(title: str) -> str:
    return _normalize_title(title) or DISCUSSION_TITLE.lower()


def _matching_key(key: str, existing: Iterable[str]) -> str | None:
    """An existing key this one is a continuation of, such as a longer subtitle."""
    words = key.split()
    for candidate in existing:
        other = candidate.split()
        shared = min(len(words), len(other))
        if shared >= MIN_PREFIX_WORDS and words[:shared] == other[:shared]:
            return candidate
    return None


def _clean_extract(extract: str) -> str:
    """Remove echoed markers, placeholder lines, and other per-segment noise."""
    lines: list[str] = []
    dropped_previous = False
    for raw in extract.strip().splitlines():
        line = _MARKER.sub("", raw).rstrip()
        if _RULE_LINE.match(line):
            continue
        content = _BULLET.sub("", line).strip()
        if not content:
            lines.append("")
            dropped_previous = False
            continue
        if _is_wrapped_continuation(line):
            if not dropped_previous:
                lines.append(line)
            continue
        dropped_previous = _is_placeholder(content)
        if dropped_previous:
            continue
        lines.append(line)
    return _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip()


def _is_placeholder(content: str) -> bool:
    plain = _EMPHASIS.sub("", content).strip()
    if plain.lower().rstrip(".!") in _EMPTY_MARKERS:
        return True
    if _TRAILING_NOISE.match(plain):
        return True
    if len(plain) > PLACEHOLDER_MAX_CHARS:
        return False
    return _PLACEHOLDER.match(plain) is not None


def _trim_blank_edges(lines: Sequence[str]) -> list[str]:
    trimmed = list(lines)
    while trimmed and not trimmed[0].strip():
        trimmed.pop(0)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed


def _normalize_line(line: str) -> str:
    text = _BULLET.sub("", line.strip())
    text = text.replace("|", " ")
    text = _TIMESTAMP.sub(" ", text)
    text = _EMPHASIS.sub("", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _significant_tokens(text: str) -> frozenset[str]:
    return frozenset(
        word
        for word in _WORD.findall(text.lower())
        if len(word) >= MIN_TOKEN_LENGTH and word not in _STOPWORDS
    )


class _LineIndex:
    """Remembers note lines so a later repeat of the same point is recognizable."""

    def __init__(self) -> None:
        self._exact: set[str] = set()
        self._token_sets: list[frozenset[str]] = []
        self._postings: dict[str, list[int]] = {}

    def add(self, line: str) -> None:
        text = _normalize_line(line)
        if not text:
            return
        self._exact.add(text)
        tokens = _significant_tokens(text)
        if len(tokens) < MIN_FUZZY_TOKENS:
            return
        position = len(self._token_sets)
        self._token_sets.append(tokens)
        for token in tokens:
            self._postings.setdefault(token, []).append(position)

    def has(self, line: str) -> bool:
        text = _normalize_line(line)
        if not text:
            return False
        if text in self._exact:
            return True
        tokens = _significant_tokens(text)
        if len(tokens) < MIN_FUZZY_TOKENS:
            return False
        for position in self._candidates(tokens):
            other = self._token_sets[position]
            if len(tokens & other) / len(tokens | other) >= NEAR_DUPLICATE_RATIO:
                return True
        return False

    def _candidates(self, tokens: Iterable[str]) -> set[int]:
        """Lines worth comparing: those sharing this line's least common tokens."""
        rarest = sorted(tokens, key=lambda token: len(self._postings.get(token, ())))
        candidates: set[int] = set()
        for token in rarest[:RARE_TOKEN_PROBES]:
            candidates.update(self._postings.get(token, ()))
        return candidates


class _CoverageIndex:
    """The vocabulary of the overview, for spotting items it already lists."""

    def __init__(self, text: str) -> None:
        self._tokens = _significant_tokens(_normalize_line(text.replace("\n", " ")))

    def covers(self, line: str) -> bool:
        tokens = _significant_tokens(_normalize_line(line))
        if len(tokens) < MIN_COVERAGE_TOKENS:
            return False
        present = sum(1 for token in tokens if token in self._tokens)
        return present / len(tokens) >= COVERAGE_RATIO
