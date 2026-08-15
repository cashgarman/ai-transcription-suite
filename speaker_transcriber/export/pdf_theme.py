from __future__ import annotations

import re
from dataclasses import dataclass, replace

from speaker_transcriber.export.meeting_document import (
    HeadingBlock,
    MeetingDocument,
)
from speaker_transcriber.prompts import normalize_style


LIGHT_MODE = "light"
DARK_MODE = "dark"
"""Which of a summary style's two accent variants a theme tints with."""

DEFAULT_THEME = "light"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class PdfPalette:
    """Colors shared by the ReportLab and WeasyPrint renderers."""

    page: str
    text: str
    muted: str
    accent: str
    accent_soft: str
    heading: str
    rule: str
    rule_strong: str
    surface: str
    surface_alt: str
    table_header_background: str
    table_header_text: str
    border: str
    participants: tuple[str, ...]


LIGHT_PALETTE = PdfPalette(
    page="#FFFFFF",
    text="#1B2429",
    muted="#5C6B73",
    accent="#1F7A8C",
    accent_soft="#E3F0F3",
    heading="#12303A",
    rule="#D3DDE1",
    rule_strong="#1F7A8C",
    surface="#F4F8F9",
    surface_alt="#EDF3F5",
    table_header_background="#1F7A8C",
    table_header_text="#FFFFFF",
    border="#C6D3D8",
    participants=(
        "#1F6FB2",
        "#B25E00",
        "#2E7D32",
        "#7B3FA0",
        "#C0392B",
        "#8D6E00",
        "#0E7C6B",
        "#4E6472",
    ),
)

DARK_PALETTE = PdfPalette(
    page="#12181C",
    text="#F4F7F8",
    muted="#9AA7AE",
    accent="#7EC8D4",
    accent_soft="#1F3239",
    heading="#7EC8D4",
    rule="#2E3A41",
    rule_strong="#7EC8D4",
    surface="#1B2429",
    surface_alt="#232D33",
    table_header_background="#245560",
    table_header_text="#F4F7F8",
    border="#2E3A41",
    participants=(
        "#9CC9F0",
        "#FFB86B",
        "#8FD48F",
        "#C89BE8",
        "#F29191",
        "#F5D77E",
        "#63C9B4",
        "#B7C3CA",
    ),
)


SEPIA_PALETTE = PdfPalette(
    page="#FBF3E4",
    text="#3B2F22",
    muted="#7A6A55",
    accent="#A0642B",
    accent_soft="#F1E3CC",
    heading="#4A3520",
    rule="#E0D2B8",
    rule_strong="#A0642B",
    surface="#F5EAD6",
    surface_alt="#EFE2CA",
    table_header_background="#7A5327",
    table_header_text="#FBF3E4",
    border="#DCCBAC",
    participants=(
        "#1D5FA8",
        "#A9500F",
        "#2F6B34",
        "#7A3E96",
        "#B03A2E",
        "#7A5B00",
        "#0F6E60",
        "#5A4A3A",
    ),
)

SLATE_PALETTE = PdfPalette(
    page="#EEF2F6",
    text="#1E2933",
    muted="#5A6B7B",
    accent="#2E6E9E",
    accent_soft="#DCE7F0",
    heading="#16242F",
    rule="#C8D4DE",
    rule_strong="#2E6E9E",
    surface="#E3EAF1",
    surface_alt="#DAE3EB",
    table_header_background="#2E6E9E",
    table_header_text="#FFFFFF",
    border="#BCCAD6",
    participants=(
        "#17568C",
        "#96540A",
        "#256B2A",
        "#66358A",
        "#A6332A",
        "#77600B",
        "#0B6558",
        "#3A4B5C",
    ),
)

MIDNIGHT_PALETTE = PdfPalette(
    page="#0E1428",
    text="#E9EDF7",
    muted="#97A2C0",
    accent="#7FA8FF",
    accent_soft="#1B2445",
    heading="#9DC0FF",
    rule="#26304F",
    rule_strong="#7FA8FF",
    surface="#161E38",
    surface_alt="#1D2745",
    table_header_background="#2A3766",
    table_header_text="#E9EDF7",
    border="#26304F",
    participants=(
        "#8FB6FF",
        "#FFC08A",
        "#93E0A8",
        "#D3A8F5",
        "#FF9C9C",
        "#F2DA8C",
        "#6FD8C6",
        "#B9C4DE",
    ),
)

CONTRAST_PALETTE = PdfPalette(
    page="#FFFFFF",
    text="#000000",
    muted="#333333",
    accent="#000000",
    accent_soft="#E6E6E6",
    heading="#000000",
    rule="#000000",
    rule_strong="#000000",
    surface="#F0F0F0",
    surface_alt="#E4E4E4",
    table_header_background="#000000",
    table_header_text="#FFFFFF",
    border="#000000",
    participants=(
        "#0033A0",
        "#8A3B00",
        "#00591F",
        "#5B0091",
        "#9E0018",
        "#4A4A00",
        "#00504B",
        "#1A1A1A",
    ),
)

MONO_PALETTE = PdfPalette(
    page="#FFFFFF",
    text="#1A1A1A",
    muted="#595959",
    accent="#4D4D4D",
    accent_soft="#EDEDED",
    heading="#262626",
    rule="#C7C7C7",
    rule_strong="#4D4D4D",
    surface="#F4F4F4",
    surface_alt="#EAEAEA",
    table_header_background="#3D3D3D",
    table_header_text="#FFFFFF",
    border="#BFBFBF",
    participants=(
        "#1A1A1A",
        "#4D4D4D",
        "#757575",
        "#2E2E2E",
        "#616161",
        "#8A8A8A",
        "#3F3F3F",
        "#6B6B6B",
    ),
)


@dataclass(frozen=True)
class PdfTheme:
    """One colour scheme offered in the PDF export dialog."""

    theme_id: str
    label: str
    description: str
    palette: PdfPalette
    mode: str = LIGHT_MODE
    tint_with_style: bool = True
    """Whether the summary style's accent colour replaces the theme's own."""


PDF_THEME_CHOICES: tuple[PdfTheme, ...] = (
    PdfTheme(
        "light",
        "Light",
        "Crisp white page. The safest choice for printing and sharing.",
        LIGHT_PALETTE,
    ),
    PdfTheme(
        "dark",
        "Dark",
        "Charcoal page that matches the app, for reading on screen.",
        DARK_PALETTE,
        mode=DARK_MODE,
    ),
    PdfTheme(
        "sepia",
        "Sepia",
        "Warm cream paper and soft brown ink, easy on the eyes for long reads.",
        SEPIA_PALETTE,
    ),
    PdfTheme(
        "slate",
        "Slate",
        "Cool blue-grey report paper with dark ink.",
        SLATE_PALETTE,
    ),
    PdfTheme(
        "midnight",
        "Midnight",
        "Deep navy page with bright accents, for presenting on a screen.",
        MIDNIGHT_PALETTE,
        mode=DARK_MODE,
    ),
    PdfTheme(
        "contrast",
        "High contrast",
        "Pure black on white with heavy rules, for maximum legibility.",
        CONTRAST_PALETTE,
        tint_with_style=False,
    ),
    PdfTheme(
        "mono",
        "Grayscale",
        "No colour at all, for black-and-white printers and photocopies.",
        MONO_PALETTE,
        tint_with_style=False,
    ),
)

PDF_THEMES: tuple[str, ...] = tuple(theme.theme_id for theme in PDF_THEME_CHOICES)

_THEMES_BY_ID = {theme.theme_id: theme for theme in PDF_THEME_CHOICES}


@dataclass(frozen=True)
class StyleAccent:
    """The colours a summary style tints onto the light or dark palette."""

    accent: str
    soft: str
    heading: str
    table_header: str


STYLE_ACCENTS: dict[str, tuple[StyleAccent, StyleAccent]] = {
    # style id: (light, dark)
    "meeting_summary": (
        StyleAccent("#1F7A8C", "#E3F0F3", "#12303A", "#1F7A8C"),
        StyleAccent("#7EC8D4", "#1F3239", "#7EC8D4", "#245560"),
    ),
    "art_meeting": (
        StyleAccent("#B4543A", "#F7E7E1", "#4A2018", "#B4543A"),
        StyleAccent("#F0A28B", "#38221C", "#F0A28B", "#6B3325"),
    ),
    "design_meeting": (
        StyleAccent("#6B4FA8", "#EDE7F8", "#2E2150", "#6B4FA8"),
        StyleAccent("#C4AEF0", "#2A2340", "#C4AEF0", "#46356F"),
    ),
    "business_meeting": (
        StyleAccent("#1F4E79", "#E3ECF5", "#10263B", "#1F4E79"),
        StyleAccent("#8FB8E0", "#1B2836", "#8FB8E0", "#24466B"),
    ),
    "casual_meeting": (
        StyleAccent("#4C7A50", "#E7F1E6", "#1F3A22", "#4C7A50"),
        StyleAccent("#9BCE9E", "#1F2C20", "#9BCE9E", "#35573A"),
    ),
    "technical_meeting": (
        StyleAccent("#46596B", "#E8ECF0", "#1E2A34", "#46596B"),
        StyleAccent("#A9BCCD", "#232C34", "#A9BCCD", "#3A4B5A"),
    ),
    "pitch_deck": (
        StyleAccent("#0E7C86", "#DFF1F2", "#062E33", "#0E7C86"),
        StyleAccent("#57D6DF", "#123033", "#57D6DF", "#12606A"),
    ),
    "internal_newsletter": (
        StyleAccent("#2A5DB0", "#E5ECF9", "#14294F", "#2A5DB0"),
        StyleAccent("#9DBDF2", "#1B2740", "#9DBDF2", "#2F4F86"),
    ),
    "external_newsletter": (
        StyleAccent("#A6791F", "#FAF1DC", "#33270A", "#A6791F"),
        StyleAccent("#E8C46A", "#33290F", "#E8C46A", "#6B5216"),
    ),
    "standup_meeting": (
        StyleAccent("#17868A", "#E1F1F1", "#0F3335", "#17868A"),
        StyleAccent("#6FD3D6", "#16302F", "#6FD3D6", "#1E5F62"),
    ),
    "pure_transcription": (
        StyleAccent("#4A5568", "#EDEFF2", "#1B2429", "#4A5568"),
        StyleAccent("#B3BDC8", "#232B33", "#B3BDC8", "#3B4653"),
    ),
    "ai_voiced_dialogue": (
        StyleAccent("#8E3D8A", "#F6E6F5", "#3A153A", "#8E3D8A"),
        StyleAccent("#E39BDF", "#2F2033", "#E39BDF", "#5E2A5C"),
    ),
}


def normalize_theme(theme: str | None) -> str:
    name = str(theme or DEFAULT_THEME).strip().lower()
    return name if name in _THEMES_BY_ID else DEFAULT_THEME


def theme_for(theme: str | None) -> PdfTheme:
    return _THEMES_BY_ID[normalize_theme(theme)]


def theme_display_name(theme: str | None) -> str:
    return theme_for(theme).label


def palette_for(theme: str | None, style: str | None = None) -> PdfPalette:
    """The theme's colours, tinted with the summary style's accent.

    Themes that opt out of tinting — the monochrome and high-contrast ones —
    keep their own colours whatever the style is.
    """
    entry = theme_for(theme)
    base = entry.palette
    accents = STYLE_ACCENTS.get(normalize_style(style))
    if accents is None or not entry.tint_with_style:
        return base
    accent = accents[1] if entry.mode == DARK_MODE else accents[0]
    return replace(
        base,
        accent=accent.accent,
        accent_soft=accent.soft,
        heading=accent.heading,
        rule_strong=accent.accent,
        table_header_background=accent.table_header,
    )


def rgb_fractions(color: str) -> tuple[float, float, float]:
    """Convert ``#RRGGBB`` into the 0-1 triple ReportLab expects."""
    value = color.lstrip("#")
    return (
        int(value[0:2], 16) / 255.0,
        int(value[2:4], 16) / 255.0,
        int(value[4:6], 16) / 255.0,
    )


@dataclass(frozen=True)
class TocEntry:
    anchor: str
    title: str
    level: int
    section_index: int
    block_index: int | None = None


def _slug(text: str) -> str:
    return _SLUG_STRIP.sub("-", text.strip().lower()).strip("-")


def toc_entries(document: MeetingDocument) -> list[TocEntry]:
    entries: list[TocEntry] = []
    used: set[str] = set()
    for index, section in enumerate(document.sections):
        if not section.title.strip():
            continue
        entries.append(
            TocEntry(
                _unique_anchor(section.title, index, used),
                section.title,
                1,
                index,
            )
        )
        for block_index, block in enumerate(section.blocks):
            if not isinstance(block, HeadingBlock):
                continue
            if not block.text.strip():
                continue
            entries.append(
                TocEntry(
                    _unique_anchor(block.text, f"{index}-{block_index}", used),
                    block.text,
                    2,
                    index,
                    block_index,
                )
            )
    return entries


def anchor_map(document: MeetingDocument) -> dict[tuple[int, int | None], str]:
    """Anchor ids keyed by ``(section index, block index or None)``."""
    return {
        (entry.section_index, entry.block_index): entry.anchor
        for entry in toc_entries(document)
    }


def _unique_anchor(title: str, index: object, used: set[str]) -> str:
    base = _slug(title) or "section"
    anchor = f"sec-{base}"
    if anchor in used:
        anchor = f"sec-{base}-{index}"
    used.add(anchor)
    return anchor


def should_render_toc(document: MeetingDocument) -> bool:
    return len(document.named_sections()) >= 2
