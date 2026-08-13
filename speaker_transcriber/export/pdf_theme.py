from __future__ import annotations

import re
from dataclasses import dataclass

from speaker_transcriber.export.meeting_document import (
    HeadingBlock,
    MeetingDocument,
)


PDF_THEMES = ("light", "dark")

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


def normalize_theme(theme: str | None) -> str:
    name = str(theme or "light").strip().lower()
    return name if name in PDF_THEMES else "light"


def palette_for(theme: str | None) -> PdfPalette:
    return DARK_PALETTE if normalize_theme(theme) == "dark" else LIGHT_PALETTE


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
