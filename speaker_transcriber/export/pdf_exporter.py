from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from speaker_transcriber.export.meeting_document import (
    ActionTableBlock,
    Block,
    BulletListBlock,
    HeadingBlock,
    MeetingDocument,
    NumberedListBlock,
    ParagraphBlock,
    RiskListBlock,
    Section,
    as_script,
    split_turn,
)
from speaker_transcriber.export.participants import (
    ParticipantHighlighter,
    build_highlighter,
)
from speaker_transcriber.export.pdf_layout import (
    MASTHEAD,
    PLAIN,
    PdfLayout,
    default_layout,
    layout_for,
)
from speaker_transcriber.export.pdf_theme import (
    PdfPalette,
    anchor_map,
    normalize_theme,
    palette_for,
    rgb_fractions,
    should_render_toc,
    toc_entries,
)

if TYPE_CHECKING:
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Table


LOGGER = logging.getLogger("speaker_transcriber.pdf")


_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(
    r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)"
)
_CODE = re.compile(r"`([^`]+)`")

_INCH = 72.0
_PAGE_WIDTH = 8.5 * _INCH
_PAGE_HEIGHT = 11 * _INCH
_LEFT_MARGIN = 0.9 * _INCH
_RIGHT_MARGIN = 0.9 * _INCH
_TOP_MARGIN = 1.0 * _INCH
_BOTTOM_MARGIN = 0.85 * _INCH
_HEADER_Y = _PAGE_HEIGHT - 0.58 * _INCH
_FOOTER_Y = 0.48 * _INCH
_CONTENT_WIDTH = _PAGE_WIDTH - _LEFT_MARGIN - _RIGHT_MARGIN

_BODY_FONT = "Helvetica"
_BOLD_FONT = "Helvetica-Bold"
_ITALIC_FONT = "Helvetica-Oblique"

_REPORTLAB_READY = False
_NumberedCanvas = None
_OutlineEntry = None
_SectionRule = None


def reportlab_available() -> bool:
    try:
        import reportlab  # noqa: F401
    except Exception:
        return False
    return True


def _missing_reportlab_message() -> str:
    return (
        "ReportLab is not installed, so the ReportLab PDF engine cannot run. "
        "Install it with `pip install reportlab`, or switch Format PDF notes "
        "to WeasyPrint if that renderer is installed."
    )


def _ensure_reportlab() -> None:
    global _REPORTLAB_READY, _NumberedCanvas, _OutlineEntry, _SectionRule
    global colors, TA_JUSTIFY, TA_LEFT, ParagraphStyle, HRFlowable, KeepTogether
    global PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    if _REPORTLAB_READY:
        return
    try:
        from reportlab.lib import colors as _colors
        from reportlab.lib.enums import TA_JUSTIFY as _ta_justify
        from reportlab.lib.enums import TA_LEFT as _ta_left
        from reportlab.lib.styles import ParagraphStyle as _paragraph_style
        from reportlab.pdfgen import canvas as _canvas
        from reportlab.platypus import (
            Flowable as _flowable,
            HRFlowable as _hr_flowable,
            KeepTogether as _keep_together,
            PageBreak as _page_break,
            Paragraph as _paragraph,
            SimpleDocTemplate as _simple_doc,
            Spacer as _spacer,
            Table as _table,
            TableStyle as _table_style,
        )
    except ImportError as exc:
        raise RuntimeError(_missing_reportlab_message()) from exc

    colors = _colors
    TA_JUSTIFY = _ta_justify
    TA_LEFT = _ta_left
    ParagraphStyle = _paragraph_style
    HRFlowable = _hr_flowable
    KeepTogether = _keep_together
    PageBreak = _page_break
    Paragraph = _paragraph
    SimpleDocTemplate = _simple_doc
    Spacer = _spacer
    Table = _table
    TableStyle = _table_style

    class NumberedCanvas(_canvas.Canvas):
        palette: PdfPalette = palette_for("light")
        header_title: str = ""
        page_width: float = _PAGE_WIDTH
        page_height: float = _PAGE_HEIGHT
        footer_label: str = ""
        bare_pages: int = 0
        """Leading pages that carry no header or footer, such as a cover."""

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._saved_page_states: list[dict] = []
            self._draw_page_background()

        def showPage(self) -> None:
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def _startPage(self) -> None:
            super()._startPage()
            self._draw_page_background()

        def save(self) -> None:
            page_count = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_chrome(page_count)
                super().showPage()
            super().save()

        def _draw_chrome(self, page_count: int) -> None:
            if self._pageNumber <= type(self).bare_pages:
                return
            palette = type(self).palette
            self._draw_header(palette)
            self._draw_footer(palette, page_count)

        def _draw_page_background(self) -> None:
            """Fill the sheet before any flowable is drawn on top of it."""
            palette = type(self).palette
            if palette.page.upper() == "#FFFFFF":
                return
            self.saveState()
            self.setFillColor(_color(palette.page))
            self.rect(
                0,
                0,
                type(self).page_width,
                type(self).page_height,
                stroke=0,
                fill=1,
            )
            self.restoreState()

        def _draw_header(self, palette: PdfPalette) -> None:
            title = type(self).header_title
            if not title:
                return
            header_y = type(self).page_height - 0.58 * _INCH
            right = type(self).page_width - _RIGHT_MARGIN
            self.setFont(_BODY_FONT, 8.5)
            self.setFillColor(_color(palette.muted))
            self.drawString(_LEFT_MARGIN, header_y, _truncate(title, 88))
            self.setStrokeColor(_color(palette.rule))
            self.setLineWidth(0.6)
            self.line(_LEFT_MARGIN, header_y - 5, right, header_y - 5)

        def _draw_footer(self, palette: PdfPalette, page_count: int) -> None:
            right = type(self).page_width - _RIGHT_MARGIN
            bare = type(self).bare_pages
            label = type(self).footer_label
            self.setStrokeColor(_color(palette.rule))
            self.setLineWidth(0.6)
            self.line(_LEFT_MARGIN, _FOOTER_Y + 12, right, _FOOTER_Y + 12)
            self.setFont(_BODY_FONT, 8.5)
            self.setFillColor(_color(palette.muted))
            if label:
                caption = f"{label} {self._pageNumber - bare}"
            else:
                caption = f"{self._pageNumber} of {page_count}"
            self.drawRightString(right, _FOOTER_Y, caption)

    class SectionRule(_hr_flowable):
        """Divider that stays hidden when a page break pushes it to the top."""

        def draw(self) -> None:
            _, y = self.canv.absolutePosition(0, 0)
            frame_top = NumberedCanvas.page_height - _TOP_MARGIN
            slack = (self.spaceBefore or 0) + (self.lineWidth or 0) + 2
            if y >= frame_top - slack:
                return
            super().draw()

    class OutlineEntry(_flowable):
        """Zero-height flowable that registers a PDF sidebar bookmark."""

        def __init__(self, anchor: str, title: str, level: int) -> None:
            super().__init__()
            self.anchor = anchor
            self.title = title
            self.level = level
            self.width = 0
            self.height = 0

        def wrap(self, available_width, available_height):
            return (0, 0)

        def draw(self) -> None:
            self.canv.bookmarkPage(self.anchor)
            self.canv.addOutlineEntry(
                _truncate(self.title, 120),
                self.anchor,
                level=self.level,
                closed=False,
            )
            self.canv.showOutline()

    _NumberedCanvas = NumberedCanvas
    _OutlineEntry = OutlineEntry
    _SectionRule = SectionRule
    _REPORTLAB_READY = True


def _color(hex_color: str):
    return colors.Color(*rgb_fractions(hex_color))


def _truncate(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _styles(
    palette: PdfPalette,
    layout: PdfLayout | None = None,
) -> dict[str, ParagraphStyle]:
    _ensure_reportlab()
    layout = layout or default_layout()
    text = _color(palette.text)
    muted = _color(palette.muted)
    heading = _color(palette.heading)
    accent = _color(palette.accent)
    slides = layout.slide_per_section
    styles = {
        "title": ParagraphStyle(
            "MeetingTitle",
            fontName=_BOLD_FONT,
            fontSize=21,
            leading=25,
            alignment=TA_LEFT,
            spaceAfter=6,
            textColor=heading,
        ),
        "subtitle": ParagraphStyle(
            "MeetingSubtitle",
            fontName=_ITALIC_FONT,
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            spaceAfter=10,
            textColor=muted,
        ),
        "meta": ParagraphStyle(
            "MeetingMeta",
            fontName=_BODY_FONT,
            fontSize=9.5,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=3,
            textColor=muted,
        ),
        "toc_title": ParagraphStyle(
            "MeetingTocTitle",
            fontName=_BOLD_FONT,
            fontSize=10,
            leading=13,
            alignment=TA_LEFT,
            spaceAfter=6,
            textColor=heading,
        ),
        "toc_entry": ParagraphStyle(
            "MeetingTocEntry",
            fontName=_BODY_FONT,
            fontSize=10,
            leading=15,
            alignment=TA_LEFT,
            textColor=text,
        ),
        "toc_subentry": ParagraphStyle(
            "MeetingTocSubEntry",
            fontName=_BODY_FONT,
            fontSize=9.5,
            leading=14,
            alignment=TA_LEFT,
            leftIndent=14,
            textColor=muted,
        ),
        "heading": ParagraphStyle(
            "MeetingHeading",
            fontName=_BOLD_FONT,
            fontSize=26 if slides else 14,
            leading=30 if slides else 18,
            alignment=TA_LEFT,
            spaceBefore=6,
            spaceAfter=16 if slides else 8,
            textColor=heading,
        ),
        "subheading": ParagraphStyle(
            "MeetingSubheading",
            fontName=_BOLD_FONT,
            fontSize=11.5,
            leading=15,
            alignment=TA_LEFT,
            spaceBefore=10,
            spaceAfter=5,
            textColor=text,
        ),
        "body": ParagraphStyle(
            "MeetingBody",
            fontName=_BODY_FONT,
            fontSize=10.5,
            leading=16,
            alignment=TA_JUSTIFY,
            spaceAfter=9,
            textColor=text,
        ),
        "risk": ParagraphStyle(
            "MeetingRisk",
            fontName=_BOLD_FONT,
            fontSize=10.5,
            leading=15,
            alignment=TA_LEFT,
            spaceAfter=3,
            textColor=text,
        ),
        "mitigation": ParagraphStyle(
            "MeetingMitigation",
            fontName=_BODY_FONT,
            fontSize=10,
            leading=15,
            alignment=TA_LEFT,
            spaceAfter=0,
            textColor=muted,
        ),
        "list": ParagraphStyle(
            "MeetingList",
            fontName=_BODY_FONT,
            fontSize=14 if slides else 10.5,
            leading=22 if slides else 16,
            alignment=TA_LEFT,
            leftIndent=24 if slides else 20,
            firstLineIndent=-16 if slides else -14,
            spaceAfter=10 if slides else 5,
            textColor=text,
        ),
        "table_header": ParagraphStyle(
            "MeetingTableHeader",
            fontName=_BOLD_FONT,
            fontSize=9.5,
            leading=13,
            alignment=TA_LEFT,
            textColor=_color(palette.table_header_text),
        ),
        "table_cell": ParagraphStyle(
            "MeetingTableCell",
            fontName=_BODY_FONT,
            fontSize=9.5,
            leading=13,
            alignment=TA_LEFT,
            textColor=text,
        ),
    }
    styles.update(
        {
            "kicker": ParagraphStyle(
                "MeetingKicker",
                fontName=_BOLD_FONT,
                fontSize=9.5,
                leading=13,
                alignment=TA_LEFT,
                spaceAfter=10,
                textColor=accent,
            ),
            "cover_title": ParagraphStyle(
                "MeetingCoverTitle",
                fontName=_BOLD_FONT,
                fontSize=34 if slides else 30,
                leading=38 if slides else 34,
                alignment=TA_LEFT,
                spaceAfter=12,
                textColor=heading,
            ),
            "cover_subtitle": ParagraphStyle(
                "MeetingCoverSubtitle",
                fontName=_ITALIC_FONT,
                fontSize=14,
                leading=19,
                alignment=TA_LEFT,
                spaceAfter=18,
                textColor=muted,
            ),
            "masthead_kicker": ParagraphStyle(
                "MeetingMastheadKicker",
                fontName=_BOLD_FONT,
                fontSize=9.5,
                leading=13,
                alignment=TA_LEFT,
                spaceAfter=6,
                textColor=_color(palette.table_header_text),
            ),
            "masthead_title": ParagraphStyle(
                "MeetingMastheadTitle",
                fontName=_BOLD_FONT,
                fontSize=25,
                leading=29,
                alignment=TA_LEFT,
                textColor=_color(palette.table_header_text),
            ),
            "lede": ParagraphStyle(
                "MeetingLede",
                fontName=_ITALIC_FONT,
                fontSize=13,
                leading=19,
                alignment=TA_LEFT,
                spaceBefore=10,
                spaceAfter=12,
                textColor=text,
            ),
            "turn": ParagraphStyle(
                "MeetingTurn",
                fontName=_BODY_FONT,
                fontSize=10.5,
                leading=15,
                alignment=TA_LEFT,
                leftIndent=54,
                firstLineIndent=-54,
                spaceAfter=7,
                textColor=text,
            ),
            "person": ParagraphStyle(
                "MeetingPerson",
                fontName=_BOLD_FONT,
                fontSize=11.5,
                leading=15,
                alignment=TA_LEFT,
                spaceAfter=4,
                textColor=heading,
            ),
        }
    )
    return styles


def markdown_to_reportlab(text: str) -> str:
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    escaped = _BOLD.sub(
        lambda match: f"<b>{match.group(1) or match.group(2) or ''}</b>",
        escaped,
    )
    escaped = _CODE.sub(r'<font name="Courier">\1</font>', escaped)
    escaped = _ITALIC.sub(
        lambda match: f"<i>{match.group(1) or match.group(2) or ''}</i>",
        escaped,
    )
    return escaped.replace("\n", "<br/>")


class _TurnColors:
    """One colour per voice in a script, assigned in order of first appearance."""

    def __init__(self, palette: PdfPalette) -> None:
        self._palette = palette
        self._assigned: dict[str, str] = {}

    def color_for(self, speaker: str) -> str:
        key = speaker.strip().lower()
        if key not in self._assigned:
            colors_available = self._palette.participants or (self._palette.accent,)
            self._assigned[key] = colors_available[
                len(self._assigned) % len(colors_available)
            ]
        return self._assigned[key]

    def speakers_in(self, document: MeetingDocument) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for section in document.sections:
            for block in section.blocks:
                if not isinstance(block, ParagraphBlock):
                    continue
                turn = split_turn(block.text)
                if turn is None:
                    continue
                name = turn[0]
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                found.append(name)
                self.color_for(name)
        return found


def _turn_paragraph(
    text: str,
    styles: dict[str, ParagraphStyle],
    turns: _TurnColors,
    highlighter: ParticipantHighlighter,
):
    """A script line with the speaker's name hanging in their own colour."""
    turn = split_turn(text)
    if turn is None:
        return Paragraph(_rich(text, highlighter), styles["body"])
    speaker, spoken = turn
    color = turns.color_for(speaker)
    return Paragraph(
        f'<b><font color="{color}">{markdown_to_reportlab(speaker)}</font></b>&nbsp;&nbsp;'
        f"{markdown_to_reportlab(spoken)}",
        styles["turn"],
    )


def _wrap_participant(text: str, color: str) -> str:
    return f'<b><font color="{color}">{text}</font></b>'


def _rich(text: str, highlighter: ParticipantHighlighter) -> str:
    return highlighter.apply(markdown_to_reportlab(text), _wrap_participant)


def _try_weasyprint_export(
    document: MeetingDocument,
    path: Path,
    theme: str,
    style: str | None,
) -> bool:
    try:
        from speaker_transcriber.export.weasyprint_exporter import (
            export_weasyprint_pdf,
            weasyprint_available,
        )

        if not weasyprint_available():
            return False
        export_weasyprint_pdf(document, path, theme=theme, style=style)
        return True
    except Exception as exc:
        LOGGER.warning("WeasyPrint export failed for %s: %s", path, exc)
        return False


def export_meeting_pdf(
    document: MeetingDocument,
    path: Path,
    engine: str = "reportlab",
    theme: str = "light",
    style: str | None = None,
) -> None:
    chosen = str(engine or "reportlab").strip().lower()
    theme = normalize_theme(theme)
    if chosen == "weasyprint":
        if _try_weasyprint_export(document, path, theme, style):
            return
        if reportlab_available():
            LOGGER.warning(
                "WeasyPrint is not available; falling back to ReportLab for %s",
                path,
            )
            _export_reportlab_pdf(document, path, theme, style)
            return
        raise RuntimeError(
            "WeasyPrint is not available. Install it and its native libraries "
            "(Pango/Cairo/GTK), or install ReportLab with `pip install reportlab`."
        )
    if reportlab_available():
        _export_reportlab_pdf(document, path, theme, style)
        return
    if _try_weasyprint_export(document, path, theme, style):
        LOGGER.warning(
            "ReportLab is not available; falling back to WeasyPrint for %s",
            path,
        )
        return
    _export_reportlab_pdf(document, path, theme, style)


def _page_size(layout: PdfLayout) -> tuple[float, float]:
    if layout.landscape:
        return (_PAGE_HEIGHT, _PAGE_WIDTH)
    return (_PAGE_WIDTH, _PAGE_HEIGHT)


def _export_reportlab_pdf(
    document: MeetingDocument,
    path: Path,
    theme: str = "light",
    style: str | None = None,
) -> None:
    _ensure_reportlab()
    layout = layout_for(style)
    palette = palette_for(theme, style)
    if layout.speaker_turns:
        document = as_script(document)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles(palette, layout)
    anchors = anchor_map(document)
    highlighter = build_highlighter(document.participants, palette.participants)
    turns = _TurnColors(palette)
    page_width, page_height = _page_size(layout)
    content_width = page_width - _LEFT_MARGIN - _RIGHT_MARGIN

    story = _front_matter_flowables(
        document,
        styles,
        palette,
        layout,
        highlighter,
        turns,
        content_width,
    )
    if layout.show_toc:
        story.extend(_toc_flowables(document, styles, palette, content_width))

    for index, section in enumerate(document.sections):
        if layout.slide_per_section and story:
            story.append(PageBreak())
        story.extend(
            _section_flowables(
                section,
                index,
                styles,
                palette,
                anchors,
                index > 0 and not layout.slide_per_section,
                highlighter,
                layout,
                turns,
                content_width,
            )
        )

    doc = SimpleDocTemplate(
        str(destination),
        pagesize=(page_width, page_height),
        leftMargin=_LEFT_MARGIN,
        rightMargin=_RIGHT_MARGIN,
        topMargin=_TOP_MARGIN,
        bottomMargin=_BOTTOM_MARGIN,
        title=document.title or layout.fallback_title,
        author="Summit",
    )
    _NumberedCanvas.palette = palette
    _NumberedCanvas.header_title = (
        "" if layout.front_matter == MASTHEAD else document.title.strip()
    )
    _NumberedCanvas.page_width = page_width
    _NumberedCanvas.page_height = page_height
    _NumberedCanvas.footer_label = layout.footer_label
    _NumberedCanvas.bare_pages = 1 if layout.has_cover_page else 0
    doc.build(story, canvasmaker=_NumberedCanvas)


def _front_matter_flowables(
    document: MeetingDocument,
    styles: dict[str, ParagraphStyle],
    palette: PdfPalette,
    layout: PdfLayout,
    highlighter: ParticipantHighlighter,
    turns: _TurnColors,
    content_width: float,
) -> list:
    """The opening of the document: a cover, a masthead, or just a title."""
    if layout.front_matter == PLAIN:
        return []
    title = document.title.strip() or layout.fallback_title
    if layout.front_matter == MASTHEAD:
        return _masthead_flowables(document, styles, palette, layout, content_width)

    cover = layout.has_cover_page
    flowables: list = []
    if cover:
        flowables.append(Spacer(1, 1.6 * _INCH))
    if layout.kicker:
        flowables.append(
            Paragraph(layout.kicker.upper(), styles["kicker"])
        )
    flowables.append(
        Paragraph(
            markdown_to_reportlab(title),
            styles["cover_title"] if cover else styles["title"],
        )
    )
    if document.subtitle.strip():
        flowables.append(
            Paragraph(
                markdown_to_reportlab(document.subtitle),
                styles["cover_subtitle"] if cover else styles["subtitle"],
            )
        )
    if layout.show_participants and document.participants.strip():
        flowables.append(
            Paragraph(
                f"<b>Participants:</b> {_rich(document.participants, highlighter)}",
                styles["meta"],
            )
        )
    if layout.show_participants and document.primary_topics.strip():
        flowables.append(
            Paragraph(
                f"<b>Primary topics:</b> "
                f"{markdown_to_reportlab(document.primary_topics)}",
                styles["meta"],
            )
        )
    legend = _legend_flowable(document, styles, turns)
    if legend is not None:
        flowables.append(legend)
    if cover:
        flowables.append(PageBreak())
    else:
        flowables.append(Spacer(1, 10))
        flowables.append(_rule(palette, palette.rule_strong, 1.2))
    return flowables


def _masthead_flowables(
    document: MeetingDocument,
    styles: dict[str, ParagraphStyle],
    palette: PdfPalette,
    layout: PdfLayout,
    content_width: float,
) -> list:
    """A newsletter banner across the top of page one, not a cover page."""
    title = document.title.strip() or layout.fallback_title
    rows = [
        [Paragraph(layout.kicker.upper(), styles["masthead_kicker"])],
        [Paragraph(markdown_to_reportlab(title), styles["masthead_title"])],
    ]
    band = Table(rows, colWidths=[content_width])
    band.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _color(palette.table_header_background)),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, 0), 14),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
                ("TOPPADDING", (0, 1), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -2), 0),
            ]
        )
    )
    band.spaceAfter = 4
    flowables: list = [band]
    if document.subtitle.strip():
        flowables.append(
            Paragraph(markdown_to_reportlab(document.subtitle), styles["lede"])
        )
    flowables.append(_rule(palette, palette.rule_strong, 1.2))
    return flowables


def _legend_flowable(
    document: MeetingDocument,
    styles: dict[str, ParagraphStyle],
    turns: _TurnColors,
):
    """A colour key for the voices in a script, when the document has any."""
    speakers = turns.speakers_in(document)
    if len(speakers) < 2:
        return None
    parts = [
        f'<b><font color="{turns.color_for(name)}">{markdown_to_reportlab(name)}</font></b>'
        for name in speakers[:4]
    ]
    return Paragraph("&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts), styles["meta"])


def _rule(palette: PdfPalette, color: str, width: float = 0.7, hide_at_top: bool = False):
    factory = _SectionRule if hide_at_top else HRFlowable
    return factory(
        width="100%",
        thickness=width,
        color=_color(color),
        spaceBefore=6,
        spaceAfter=10,
        lineCap="round",
    )


def _toc_flowables(
    document: MeetingDocument,
    styles: dict[str, ParagraphStyle],
    palette: PdfPalette,
    content_width: float = _CONTENT_WIDTH,
) -> list:
    if not should_render_toc(document):
        return []
    entries = toc_entries(document)
    if not entries:
        return []
    rows: list[list] = [[Paragraph("Contents", styles["toc_title"])]]
    for entry in entries:
        style = styles["toc_entry"] if entry.level == 1 else styles["toc_subentry"]
        rows.append(
            [
                Paragraph(
                    f'<link href="#{entry.anchor}" color="{palette.accent}">'
                    f"{markdown_to_reportlab(entry.title)}</link>",
                    style,
                )
            ]
        )
    table = Table(rows, colWidths=[content_width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _color(palette.surface)),
                ("BOX", (0, 0), (-1, -1), 0.6, _color(palette.border)),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (0, 0), 10),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
            ]
        )
    )
    table.spaceAfter = 6
    return [table, _rule(palette, palette.rule)]


def _section_flowables(
    section: Section,
    section_index: int,
    styles: dict[str, ParagraphStyle],
    palette: PdfPalette,
    anchors: dict[tuple[int, int | None], str],
    with_divider: bool,
    highlighter: ParticipantHighlighter | None = None,
    layout: PdfLayout | None = None,
    turns: _TurnColors | None = None,
    content_width: float = _CONTENT_WIDTH,
) -> list:
    highlighter = highlighter or ParticipantHighlighter()
    layout = layout or default_layout()
    turns = turns or _TurnColors(palette)
    flowables: list = []
    body: list = []
    if layout.person_cards and _has_person_headings(section):
        body = _person_card_flowables(
            section,
            section_index,
            styles,
            palette,
            anchors,
            highlighter,
            layout,
            turns,
            content_width,
        )
    else:
        for block_index, block in enumerate(section.blocks):
            body.extend(
                _block_flowables(
                    block,
                    styles,
                    palette,
                    anchors.get((section_index, block_index), ""),
                    highlighter,
                    layout,
                    turns,
                    content_width,
                )
            )
    if section.title.strip():
        anchor = anchors.get((section_index, None), "")
        heading = Paragraph(
            f'<a name="{anchor}"/>{markdown_to_reportlab(section.title)}',
            styles["heading"],
        )
        opening: list = [_OutlineEntry(f"{anchor}-outline", section.title, 0), heading]
        if with_divider:
            opening.insert(0, _rule(palette, palette.rule, hide_at_top=True))
        if body:
            opening.append(body[0])
            body = body[1:]
        flowables.append(KeepTogether(opening))
    elif with_divider and body:
        flowables.append(_rule(palette, palette.rule, hide_at_top=True))
    flowables.extend(body)
    return flowables


def _has_person_headings(section: Section) -> bool:
    return any(
        isinstance(block, HeadingBlock) and block.level >= 3
        for block in section.blocks
    )


def _person_card_flowables(
    section: Section,
    section_index: int,
    styles: dict[str, ParagraphStyle],
    palette: PdfPalette,
    anchors: dict[tuple[int, int | None], str],
    highlighter: ParticipantHighlighter,
    layout: PdfLayout,
    turns: _TurnColors,
    content_width: float,
) -> list:
    """Each `###` person and their update as one card that cannot be split."""
    flowables: list = []
    card: list = []

    def flush() -> None:
        nonlocal card
        if card:
            flowables.append(_surface_card(card, palette, content_width))
            card = []

    for block_index, block in enumerate(section.blocks):
        anchor = anchors.get((section_index, block_index), "")
        if isinstance(block, HeadingBlock) and block.level >= 3:
            flush()
            prefix = f'<a name="{anchor}"/>' if anchor else ""
            card.append(
                Paragraph(
                    f"{prefix}{markdown_to_reportlab(block.text)}",
                    styles["person"],
                )
            )
            continue
        rendered = _block_flowables(
            block,
            styles,
            palette,
            anchor,
            highlighter,
            layout,
            turns,
            content_width,
        )
        if card:
            card.extend(rendered)
        else:
            flowables.extend(rendered)
    flush()
    return flowables


def _surface_card(flowables: list, palette: PdfPalette, content_width: float):
    card = Table([[item] for item in flowables], colWidths=[content_width])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _color(palette.surface)),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, _color(palette.accent)),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
                ("TOPPADDING", (0, 1), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -2), 2),
            ]
        )
    )
    card.spaceAfter = 8
    return KeepTogether([card])


def _block_flowables(
    block: Block,
    styles: dict[str, ParagraphStyle],
    palette: PdfPalette,
    anchor: str = "",
    highlighter: ParticipantHighlighter | None = None,
    layout: PdfLayout | None = None,
    turns: _TurnColors | None = None,
    content_width: float = _CONTENT_WIDTH,
) -> list:
    highlighter = highlighter or ParticipantHighlighter()
    layout = layout or default_layout()
    turns = turns or _TurnColors(palette)
    if isinstance(block, ParagraphBlock):
        if not block.text.strip():
            return []
        if layout.speaker_turns:
            return [_turn_paragraph(block.text, styles, turns, highlighter)]
        return [Paragraph(_rich(block.text, highlighter), styles["body"])]
    if isinstance(block, HeadingBlock):
        style = styles["subheading"] if block.level >= 3 else styles["heading"]
        prefix = f'<a name="{anchor}"/>' if anchor else ""
        heading = Paragraph(f"{prefix}{markdown_to_reportlab(block.text)}", style)
        if not anchor:
            return [heading]
        return [
            KeepTogether(
                [_OutlineEntry(f"{anchor}-outline", block.text, 1), heading]
            )
        ]
    if isinstance(block, NumberedListBlock):
        return _list_flowables(
            block.items, styles, palette, numbered=True, highlighter=highlighter
        )
    if isinstance(block, BulletListBlock):
        return _list_flowables(
            block.items, styles, palette, numbered=False, highlighter=highlighter
        )
    if isinstance(block, ActionTableBlock):
        return [_action_table(block, styles, palette, highlighter, content_width)]
    if isinstance(block, RiskListBlock):
        return _risk_flowables(block, styles, palette, highlighter, content_width)
    return []


def _list_flowables(
    items: list[str],
    styles: dict[str, ParagraphStyle],
    palette: PdfPalette,
    numbered: bool,
    highlighter: ParticipantHighlighter | None = None,
) -> list:
    highlighter = highlighter or ParticipantHighlighter()
    entries = [item for item in items if item.strip()]
    if not entries:
        return []
    flowables: list = []
    for position, item in enumerate(entries, start=1):
        marker = f"{position}." if numbered else "\u2022"
        flowables.append(
            Paragraph(
                f'<font color="{palette.accent}"><b>{marker}</b></font>&nbsp;&nbsp;'
                f"{_rich(item, highlighter)}",
                styles["list"],
            )
        )
    flowables.append(Spacer(1, 5))
    return flowables


def _action_table(
    block: ActionTableBlock,
    styles: dict[str, ParagraphStyle],
    palette: PdfPalette,
    highlighter: ParticipantHighlighter | None = None,
    content_width: float = _CONTENT_WIDTH,
) -> Table:
    highlighter = highlighter or ParticipantHighlighter()
    header = [
        Paragraph("Owner", styles["table_header"]),
        Paragraph("Action", styles["table_header"]),
        Paragraph("Priority", styles["table_header"]),
    ]
    data = [header]
    for row in block.rows:
        data.append(
            [
                Paragraph(_rich(row.owner or "—", highlighter), styles["table_cell"]),
                Paragraph(_rich(row.action or "—", highlighter), styles["table_cell"]),
                Paragraph(
                    markdown_to_reportlab(row.priority or "—"),
                    styles["table_cell"],
                ),
            ]
        )
    owner_width = 1.25 * _INCH
    priority_width = 0.95 * _INCH
    action_width = content_width - owner_width - priority_width
    table = Table(
        data,
        colWidths=[owner_width, action_width, priority_width],
        repeatRows=1,
    )
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), _color(palette.table_header_background)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, _color(palette.border)),
        ("ALIGN", (2, 1), (2, -1), "LEFT"),
    ]
    for index in range(1, len(data)):
        if index % 2 == 0:
            commands.append(
                ("BACKGROUND", (0, index), (-1, index), _color(palette.surface))
            )
    table.setStyle(TableStyle(commands))
    table.spaceAfter = 12
    return table


def _risk_flowables(
    block: RiskListBlock,
    styles: dict[str, ParagraphStyle],
    palette: PdfPalette,
    highlighter: ParticipantHighlighter | None = None,
    content_width: float = _CONTENT_WIDTH,
) -> list:
    highlighter = highlighter or ParticipantHighlighter()
    flowables: list = []
    for item in block.items:
        rows: list[list] = []
        if item.text.strip():
            rows.append([Paragraph(_rich(item.text, highlighter), styles["risk"])])
        if item.mitigation.strip():
            rows.append(
                [
                    Paragraph(
                        f"<b>Mitigation:</b> {_rich(item.mitigation, highlighter)}",
                        styles["mitigation"],
                    )
                ]
            )
        if not rows:
            continue
        card = Table(rows, colWidths=[content_width])
        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _color(palette.surface)),
                    ("LINEBEFORE", (0, 0), (0, -1), 2.5, _color(palette.accent)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, 0), 8),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
                    ("TOPPADDING", (0, 1), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -2), 2),
                ]
            )
        )
        card.spaceAfter = 8
        flowables.append(card)
    return flowables
