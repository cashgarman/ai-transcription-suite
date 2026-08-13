"""Summarization prompt packs, one per summary style.

Every style owns a full pack (`system`, `chunk`, `merge`, `validate`, `format`)
so that both the per-segment extraction pass and the final document match the
style the user asked for. Only `continue.txt` is shared: finishing a truncated
generation is the same job no matter what is being written.
"""

from __future__ import annotations

import logging
import sys
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


@dataclass(frozen=True)
class SummaryStyle:
    style_id: str
    display_name: str
    description: str
    pipeline: str = MEETING_PIPELINE
    required_sections: tuple[str, ...] = ()
    uses_running_outline: bool = True
    """Whether a segment is told what earlier segments already covered."""

    @property
    def is_meeting_family(self) -> bool:
        return self.pipeline == MEETING_PIPELINE

    @property
    def keeps_segment_notes(self) -> bool:
        return self.pipeline in (MEETING_PIPELINE, SEQUENTIAL_PIPELINE)


_MEETING_SECTIONS = ("action items", "open questions")

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
    ),
    SummaryStyle(
        "pitch_deck",
        "Pitch Deck",
        "Slide-ready outline: problem, solution, proof, ask.",
        pipeline=DOCUMENT_PIPELINE,
    ),
    SummaryStyle(
        "internal_newsletter",
        "Internal Newsletter",
        "Candid team update with owners and shoutouts.",
        pipeline=DOCUMENT_PIPELINE,
    ),
    SummaryStyle(
        "external_newsletter",
        "External Newsletter",
        "Polished customer-facing update with no internals.",
        pipeline=DOCUMENT_PIPELINE,
    ),
    SummaryStyle(
        "technical_meeting",
        "Technical Meeting",
        "Decision record: problem, options, decision, consequences.",
        pipeline=DOCUMENT_PIPELINE,
        required_sections=("decision",),
    ),
    SummaryStyle(
        "art_meeting",
        "Art Meeting",
        "Meeting notes focused on visual direction and asset feedback.",
        required_sections=_MEETING_SECTIONS,
    ),
    SummaryStyle(
        "design_meeting",
        "Design Meeting",
        "Meeting notes focused on problem framing and what to prototype.",
        required_sections=_MEETING_SECTIONS,
    ),
    SummaryStyle(
        "business_meeting",
        "Business Meeting",
        "Meeting notes focused on goals, numbers, and commercial decisions.",
        required_sections=_MEETING_SECTIONS,
    ),
    SummaryStyle(
        "casual_meeting",
        "Casual Meeting",
        "The same facts as a meeting summary, told as a warm recap.",
        required_sections=_MEETING_SECTIONS,
    ),
    SummaryStyle(
        "standup_meeting",
        "Stand-Up Meeting",
        "Per-person yesterday/today/blockers plus team themes.",
        pipeline=DOCUMENT_PIPELINE,
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
