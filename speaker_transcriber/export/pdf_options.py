"""User-facing options for how a notes PDF is generated.

The options are registry-driven, like the summary sections: the export dialog,
the settings validation, and both PDF engines read this table. Adding an
option means one new ``PdfOption`` entry here plus its effect in
``apply_pdf_options``; the dialog and persistence pick it up unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from speaker_transcriber.export.pdf_layout import (
    COMPACT,
    COVER,
    PdfLayout,
    layout_for,
)
from speaker_transcriber.export.pdf_theme import normalize_theme


COVER_PAGE_OPTION = "cover_page"


@dataclass(frozen=True)
class PdfOption:
    """One toggle in the PDF export dialog."""

    option_id: str
    label: str
    description: str
    default: bool = True
    needs_front_matter: tuple[str, ...] = ()
    """Offer the option only for styles whose layout opens one of these ways."""


PDF_OPTIONS: tuple[PdfOption, ...] = (
    PdfOption(
        COVER_PAGE_OPTION,
        "Large cover page",
        "A full title page before the notes. When off, the document opens "
        "with a compact heading at the top of page one.",
        needs_front_matter=(COVER,),
    ),
)

_OPTIONS_BY_ID = {option.option_id: option for option in PDF_OPTIONS}


def pdf_option_defaults() -> dict[str, bool]:
    return {option.option_id: option.default for option in PDF_OPTIONS}


def effective_pdf_options(stored: Mapping[str, object] | None) -> dict[str, bool]:
    """The defaults overlaid with stored choices; unknown keys are dropped."""
    values = pdf_option_defaults()
    for key, value in (stored or {}).items():
        if str(key) in _OPTIONS_BY_ID and isinstance(value, bool):
            values[str(key)] = value
    return values


def pdf_option_deviations(values: Mapping[str, object] | None) -> dict[str, bool]:
    """The subset of ``values`` that differs from the defaults, for storage.

    Persisting only deviations means a future change to an option's default
    reaches every user who never touched that option.
    """
    effective = effective_pdf_options(values)
    return {
        option.option_id: effective[option.option_id]
        for option in PDF_OPTIONS
        if effective[option.option_id] != option.default
    }


def applicable_pdf_options(style: str | None) -> tuple[PdfOption, ...]:
    """The options that make a difference for this style's layout."""
    front_matter = layout_for(style).front_matter
    return tuple(
        option
        for option in PDF_OPTIONS
        if not option.needs_front_matter
        or front_matter in option.needs_front_matter
    )


@dataclass(frozen=True)
class PdfExportChoices:
    """Everything the export dialog collects: the colour theme and the toggles."""

    theme: str
    options: dict[str, bool]

    @classmethod
    def build(
        cls,
        theme: str | None,
        options: Mapping[str, object] | None = None,
    ) -> "PdfExportChoices":
        return cls(normalize_theme(theme), effective_pdf_options(options))


def apply_pdf_options(
    layout: PdfLayout,
    options: Mapping[str, object] | None,
) -> PdfLayout:
    """The layout with every disabled feature turned off.

    Both PDF engines call this on the style's layout before rendering, so an
    option affects ReportLab and WeasyPrint output identically.
    """
    values = effective_pdf_options(options)
    if not values[COVER_PAGE_OPTION] and layout.front_matter == COVER:
        layout = replace(layout, front_matter=COMPACT)
    return layout
