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
_TOP_MARGIN = 0.85 * _INCH
_BOTTOM_MARGIN = 0.85 * _INCH
_FOOTER_Y = 0.48 * _INCH
_CONTENT_WIDTH = _PAGE_WIDTH - _LEFT_MARGIN - _RIGHT_MARGIN

_REPORTLAB_READY = False
_NumberedCanvas = None


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
    global _REPORTLAB_READY, _NumberedCanvas
    global colors, TA_JUSTIFY, TA_LEFT, ParagraphStyle, ListFlowable
    global ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    if _REPORTLAB_READY:
        return
    try:
        from reportlab.lib import colors as _colors
        from reportlab.lib.enums import TA_JUSTIFY as _ta_justify
        from reportlab.lib.enums import TA_LEFT as _ta_left
        from reportlab.lib.styles import ParagraphStyle as _paragraph_style
        from reportlab.pdfgen import canvas as _canvas
        from reportlab.platypus import (
            ListFlowable as _list_flowable,
            ListItem as _list_item,
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
    ListFlowable = _list_flowable
    ListItem = _list_item
    Paragraph = _paragraph
    SimpleDocTemplate = _simple_doc
    Spacer = _spacer
    Table = _table
    TableStyle = _table_style

    class NumberedCanvas(_canvas.Canvas):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._saved_page_states: list[dict] = []

        def showPage(self) -> None:
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            page_count = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_page_number(page_count)
                super().showPage()
            super().save()

        def _draw_page_number(self, page_count: int) -> None:
            self.setFont("Times-Roman", 9)
            self.setFillColor(colors.Color(0.25, 0.25, 0.25))
            label = f"-- {self._pageNumber} of {page_count} --"
            self.drawCentredString(_PAGE_WIDTH / 2.0, _FOOTER_Y, label)

    _NumberedCanvas = NumberedCanvas
    _REPORTLAB_READY = True


def _styles() -> dict[str, ParagraphStyle]:
    _ensure_reportlab()
    return {
        "title": ParagraphStyle(
            "MeetingTitle",
            fontName="Times-Bold",
            fontSize=18,
            leading=22,
            alignment=TA_LEFT,
            spaceAfter=8,
            textColor=colors.black,
        ),
        "subtitle": ParagraphStyle(
            "MeetingSubtitle",
            fontName="Times-Italic",
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            spaceAfter=12,
            textColor=colors.black,
        ),
        "meta": ParagraphStyle(
            "MeetingMeta",
            fontName="Times-Roman",
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "heading": ParagraphStyle(
            "MeetingHeading",
            fontName="Times-Bold",
            fontSize=13,
            leading=17,
            alignment=TA_LEFT,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "subheading": ParagraphStyle(
            "MeetingSubheading",
            fontName="Times-Bold",
            fontSize=11.5,
            leading=15,
            alignment=TA_LEFT,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "MeetingBody",
            fontName="Times-Roman",
            fontSize=11,
            leading=15,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        ),
        "risk": ParagraphStyle(
            "MeetingRisk",
            fontName="Times-Roman",
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "mitigation": ParagraphStyle(
            "MeetingMitigation",
            fontName="Times-Roman",
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
            leftIndent=12,
            spaceAfter=8,
        ),
        "list": ParagraphStyle(
            "MeetingList",
            fontName="Times-Roman",
            fontSize=11,
            leading=15,
            alignment=TA_LEFT,
        ),
        "table_header": ParagraphStyle(
            "MeetingTableHeader",
            fontName="Times-Bold",
            fontSize=10,
            leading=13,
            alignment=TA_LEFT,
        ),
        "table_cell": ParagraphStyle(
            "MeetingTableCell",
            fontName="Times-Roman",
            fontSize=10,
            leading=13,
            alignment=TA_LEFT,
        ),
    }


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


def _try_weasyprint_export(document: MeetingDocument, path: Path) -> bool:
    try:
        from speaker_transcriber.export.weasyprint_exporter import (
            export_weasyprint_pdf,
            weasyprint_available,
        )

        if not weasyprint_available():
            return False
        export_weasyprint_pdf(document, path)
        return True
    except Exception as exc:
        LOGGER.warning("WeasyPrint export failed for %s: %s", path, exc)
        return False


def export_meeting_pdf(
    document: MeetingDocument,
    path: Path,
    engine: str = "reportlab",
) -> None:
    chosen = str(engine or "reportlab").strip().lower()
    if chosen == "weasyprint":
        if _try_weasyprint_export(document, path):
            return
        if reportlab_available():
            LOGGER.warning(
                "WeasyPrint is not available; falling back to ReportLab for %s",
                path,
            )
            _export_reportlab_pdf(document, path)
            return
        raise RuntimeError(
            "WeasyPrint is not available. Install it and its native libraries "
            "(Pango/Cairo/GTK), or install ReportLab with `pip install reportlab`."
        )
    if reportlab_available():
        _export_reportlab_pdf(document, path)
        return
    if _try_weasyprint_export(document, path):
        LOGGER.warning(
            "ReportLab is not available; falling back to WeasyPrint for %s",
            path,
        )
        return
    _export_reportlab_pdf(document, path)


def _export_reportlab_pdf(document: MeetingDocument, path: Path) -> None:
    _ensure_reportlab()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    story: list = []

    if document.title.strip():
        story.append(Paragraph(markdown_to_reportlab(document.title), styles["title"]))
    if document.subtitle.strip():
        story.append(
            Paragraph(markdown_to_reportlab(document.subtitle), styles["subtitle"])
        )
    if document.participants.strip():
        story.append(
            Paragraph(
                f"<b>Participants:</b> {markdown_to_reportlab(document.participants)}",
                styles["meta"],
            )
        )
    if document.primary_topics.strip():
        story.append(
            Paragraph(
                f"<b>Primary topics:</b> {markdown_to_reportlab(document.primary_topics)}",
                styles["meta"],
            )
        )
        story.append(Spacer(1, 6))

    for section in document.sections:
        story.extend(_section_flowables(section, styles))

    doc = SimpleDocTemplate(
        str(destination),
        pagesize=(_PAGE_WIDTH, _PAGE_HEIGHT),
        leftMargin=_LEFT_MARGIN,
        rightMargin=_RIGHT_MARGIN,
        topMargin=_TOP_MARGIN,
        bottomMargin=_BOTTOM_MARGIN,
        title=document.title or destination.stem,
        author="Summit",
    )
    doc.build(story, canvasmaker=_NumberedCanvas)


def _section_flowables(section: Section, styles: dict[str, ParagraphStyle]) -> list:
    flowables: list = []
    if section.title.strip():
        flowables.append(
            Paragraph(markdown_to_reportlab(section.title), styles["heading"])
        )
    for block in section.blocks:
        flowables.extend(_block_flowables(block, styles))
    return flowables


def _block_flowables(block: Block, styles: dict[str, ParagraphStyle]) -> list:
    if isinstance(block, ParagraphBlock):
        if not block.text.strip():
            return []
        return [Paragraph(markdown_to_reportlab(block.text), styles["body"])]
    if isinstance(block, HeadingBlock):
        style = styles["subheading"] if block.level >= 3 else styles["heading"]
        return [Paragraph(markdown_to_reportlab(block.text), style)]
    if isinstance(block, NumberedListBlock):
        return _list_flowable(block.items, styles, bullet_type="1")
    if isinstance(block, BulletListBlock):
        return _list_flowable(block.items, styles, bullet_type="bullet")
    if isinstance(block, ActionTableBlock):
        return [_action_table(block, styles)]
    if isinstance(block, RiskListBlock):
        return _risk_flowables(block, styles)
    return []


def _list_flowable(
    items: list[str],
    styles: dict[str, ParagraphStyle],
    bullet_type: str,
) -> list:
    entries = [
        ListItem(
            Paragraph(markdown_to_reportlab(item), styles["list"]),
            leftIndent=18,
            value="bullet" if bullet_type == "bullet" else None,
        )
        for item in items
        if item.strip()
    ]
    if not entries:
        return []
    return [
        ListFlowable(
            entries,
            bulletType="bullet" if bullet_type == "bullet" else "1",
            start="1",
            leftIndent=18,
            bulletFontName="Times-Roman",
            bulletFontSize=11,
            spaceAfter=8,
        )
    ]


def _action_table(
    block: ActionTableBlock,
    styles: dict[str, ParagraphStyle],
) -> Table:
    header = [
        Paragraph("Owner", styles["table_header"]),
        Paragraph("Action", styles["table_header"]),
        Paragraph("Priority", styles["table_header"]),
    ]
    data = [header]
    for row in block.rows:
        data.append(
            [
                Paragraph(markdown_to_reportlab(row.owner or "—"), styles["table_cell"]),
                Paragraph(markdown_to_reportlab(row.action or "—"), styles["table_cell"]),
                Paragraph(
                    markdown_to_reportlab(row.priority or "—"),
                    styles["table_cell"],
                ),
            ]
        )
    owner_width = 1.25 * _INCH
    priority_width = 0.95 * _INCH
    action_width = _CONTENT_WIDTH - owner_width - priority_width
    table = Table(
        data,
        colWidths=[owner_width, action_width, priority_width],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.93, 0.93)),
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.Color(0.55, 0.55, 0.55)),
                ("ALIGN", (2, 1), (2, -1), "LEFT"),
            ]
        )
    )
    table.spaceAfter = 10
    return table


def _risk_flowables(
    block: RiskListBlock,
    styles: dict[str, ParagraphStyle],
) -> list:
    flowables: list = []
    for item in block.items:
        if item.text.strip():
            flowables.append(
                Paragraph(markdown_to_reportlab(item.text), styles["risk"])
            )
        if item.mitigation.strip():
            flowables.append(
                Paragraph(
                    f"<b>Mitigation:</b> {markdown_to_reportlab(item.mitigation)}",
                    styles["mitigation"],
                )
            )
        elif item.text.strip():
            flowables.append(Spacer(1, 6))
    return flowables
