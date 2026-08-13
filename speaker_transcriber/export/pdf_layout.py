"""How each summary style is laid out on the page.

The PDF theme (light or dark) stays the user's choice; the summary style picks
the shape of the document: a cover page for meeting notes, a masthead for a
newsletter, landscape slides for a pitch deck, a bare script for a transcript.
Both renderers read this table so the two engines produce the same document.
"""

from __future__ import annotations

from dataclasses import dataclass

from speaker_transcriber.prompts import DEFAULT_STYLE, normalize_style


COVER = "cover"
"""A dedicated first page, followed by a page break."""

MASTHEAD = "masthead"
"""A banner at the top of page one, with the body flowing under it."""

COMPACT = "compact"
"""A small titled header band, no page break."""

PLAIN = "plain"
"""No front matter beyond a running title."""


@dataclass(frozen=True)
class PdfLayout:
    kind: str
    kicker: str
    fallback_title: str
    front_matter: str = COVER
    landscape: bool = False
    show_toc: bool = True
    slide_per_section: bool = False
    show_participants: bool = True
    speaker_turns: bool = False
    person_cards: bool = False
    footer_label: str = ""

    @property
    def has_cover_page(self) -> bool:
        return self.front_matter == COVER


_MEETING_KINDS = {
    "meeting_summary": ("meeting_cover", "Meeting notes"),
    "art_meeting": ("meeting_cover", "Art review"),
    "design_meeting": ("meeting_cover", "Design review"),
    "business_meeting": ("meeting_cover", "Business review"),
    "casual_meeting": ("meeting_cover", "Team catch-up"),
}

LAYOUTS: dict[str, PdfLayout] = {
    style_id: PdfLayout(kind, kicker, "Meeting Notes")
    for style_id, (kind, kicker) in _MEETING_KINDS.items()
}

LAYOUTS.update(
    {
        "technical_meeting": PdfLayout(
            "adr_cover",
            "Decision record",
            "Technical Decision Record",
        ),
        "pitch_deck": PdfLayout(
            "pitch_slides",
            "Pitch",
            "Pitch Deck",
            landscape=True,
            show_toc=False,
            slide_per_section=True,
            show_participants=False,
            footer_label="Slide",
        ),
        "internal_newsletter": PdfLayout(
            "newsletter",
            "Team update",
            "Internal Newsletter",
            front_matter=MASTHEAD,
            show_toc=False,
            show_participants=False,
        ),
        "external_newsletter": PdfLayout(
            "newsletter",
            "Customer update",
            "Newsletter",
            front_matter=MASTHEAD,
            show_toc=False,
            show_participants=False,
        ),
        "standup_meeting": PdfLayout(
            "standup",
            "Stand-up",
            "Stand-Up Notes",
            front_matter=COMPACT,
            show_toc=False,
            person_cards=True,
        ),
        "pure_transcription": PdfLayout(
            "transcript",
            "Transcript",
            "Transcript",
            front_matter=PLAIN,
            show_toc=False,
            show_participants=False,
            speaker_turns=True,
        ),
        "ai_voiced_dialogue": PdfLayout(
            "dialogue",
            "Voiced dialogue",
            "Voiced Dialogue",
            front_matter=COMPACT,
            show_toc=False,
            show_participants=False,
            speaker_turns=True,
        ),
    }
)


def layout_for(style: str | None) -> PdfLayout:
    return LAYOUTS[normalize_style(style)]


def layout_kind(style: str | None) -> str:
    return layout_for(style).kind


def default_layout() -> PdfLayout:
    return LAYOUTS[DEFAULT_STYLE]
