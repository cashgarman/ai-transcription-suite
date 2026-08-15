"""Render a Markdown document from `docs/` to a themed PDF.

WeasyPrint gives better output but needs GTK native libraries that are often
missing on Windows, so this uses ReportLab. Colours come from the application's
own PDF palette so generated documents match the meeting notes Summit exports.

    python scripts/render_doc_pdf.py docs/code-review.md
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from speaker_transcriber.export.pdf_theme import palette_for

LEFT_MARGIN = 0.9 * inch
RIGHT_MARGIN = 0.9 * inch
TOP_MARGIN = 0.95 * inch
BOTTOM_MARGIN = 0.85 * inch

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*]\s+(.*)$")
_TABLE_RULE = re.compile(r"^\|[\s:|-]+\|$")
_CODE_CAPTION = re.compile(r"^(\d+):(\d+):(.+)$")
_CODE_SPAN = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_PLACEHOLDER = re.compile("\x00(\\d+)\x00")


@dataclass
class Block:
    kind: str
    level: int = 0
    lines: list[str] = field(default_factory=list)
    caption: str = ""


def parse_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if stripped.startswith("```"):
            caption = stripped[3:].strip()
            index += 1
            body: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                body.append(lines[index])
                index += 1
            index += 1
            blocks.append(Block("code", lines=body, caption=caption))
            continue

        if not stripped:
            index += 1
            continue

        heading = _HEADING.match(stripped)
        if heading:
            blocks.append(
                Block("heading", level=len(heading.group(1)), lines=[heading.group(2)])
            )
            index += 1
            continue

        if stripped.startswith("|"):
            rows: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(lines[index].strip())
                index += 1
            blocks.append(Block("table", lines=rows))
            continue

        if _BULLET.match(raw):
            items: list[str] = []
            while index < len(lines):
                bullet = _BULLET.match(lines[index])
                if bullet:
                    items.append(bullet.group(2).strip())
                elif lines[index].strip() and lines[index].startswith(("  ", "\t")) and items:
                    # A wrapped continuation line belongs to the bullet above it.
                    items[-1] += " " + lines[index].strip()
                else:
                    break
                index += 1
            blocks.append(Block("bullets", lines=items))
            continue

        paragraph: list[str] = []
        while index < len(lines):
            current = lines[index]
            if not current.strip():
                break
            if current.strip().startswith(("#", "|", "```")) or _BULLET.match(current):
                break
            paragraph.append(current.strip())
            index += 1
        blocks.append(Block("para", lines=[" ".join(paragraph)]))

    return blocks


def inline(text: str) -> str:
    """Markdown inline markup to ReportLab markup, with links flattened to text.

    Code spans are set aside before emphasis is applied. Doing it the other way
    round lets an underscore inside one span pair with an underscore inside the
    next and emit `<i>` tags that interleave with the `<font>` tags, which
    ReportLab rejects outright.
    """
    spans: list[str] = []

    def stash(match: re.Match[str]) -> str:
        spans.append(_escape(match.group(1)))
        return f"\x00{len(spans) - 1}\x00"

    text = _CODE_SPAN.sub(stash, _LINK.sub(r"\1", text))
    text = _ITALIC.sub(r"<i>\1</i>", _BOLD.sub(r"<b>\1</b>", _escape(text)))
    return _PLACEHOLDER.sub(
        lambda match: f'<font name="Courier">{spans[int(match.group(1))]}</font>',
        text,
    )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table_rows(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for raw in lines:
        if _TABLE_RULE.match(raw):
            continue
        rows.append([cell.strip() for cell in raw.strip().strip("|").split("|")])
    return rows


def build_styles(palette) -> dict[str, ParagraphStyle]:
    text = colors.HexColor(palette.text)
    heading = colors.HexColor(palette.heading)
    accent = colors.HexColor(palette.accent)
    muted = colors.HexColor(palette.muted)

    body = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=9.6,
        leading=14.4,
        textColor=text,
        spaceAfter=8,
    )
    return {
        "title": ParagraphStyle(
            "title",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=27,
            textColor=heading,
            spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=accent,
            spaceBefore=18,
            spaceAfter=7,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=11.6,
            leading=15,
            textColor=heading,
            spaceBefore=13,
            spaceAfter=5,
        ),
        "h4": ParagraphStyle(
            "h4",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=10.2,
            leading=13.5,
            textColor=text,
            spaceBefore=11,
            spaceAfter=4,
        ),
        "body": body,
        "bullet": ParagraphStyle(
            "bullet",
            parent=body,
            leftIndent=14,
            bulletIndent=3,
            spaceAfter=4.5,
        ),
        "code": ParagraphStyle(
            "code",
            fontName="Courier",
            fontSize=8.0,
            leading=10.4,
            textColor=text,
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=body,
            fontName="Helvetica-Oblique",
            fontSize=8.2,
            leading=10.5,
            textColor=muted,
            spaceAfter=2,
        ),
        "cell": ParagraphStyle(
            "cell",
            parent=body,
            fontSize=9.0,
            leading=12.4,
            spaceAfter=0,
        ),
        "cell_head": ParagraphStyle(
            "cell_head",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=9.0,
            leading=12.4,
            textColor=colors.HexColor(palette.table_header_text),
            spaceAfter=0,
        ),
    }


def code_caption(caption: str) -> str:
    """Caption a fence only when its info string names a source location.

    A bare language tag such as `text` or `python` is not worth showing.
    """
    match = _CODE_CAPTION.match(caption)
    if not match:
        return ""
    start, end, path = match.groups()
    return f"{path} \u2014 lines {start}\u2013{end}"


def code_flowable(block: Block, styles, palette, width: float):
    body = "\n".join(block.lines).rstrip()
    inner = Preformatted(body, styles["code"])
    frame = Table([[inner]], colWidths=[width])
    frame.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(palette.surface)),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor(palette.border)),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    parts = []
    caption = code_caption(block.caption)
    if caption:
        parts.append(Paragraph(inline(caption), styles["caption"]))
    parts.extend([frame, Spacer(1, 9)])
    return KeepTogether(parts)


def table_flowable(block: Block, styles, palette, width: float):
    rows = table_rows(block.lines)
    if not rows:
        return Spacer(1, 0)
    header, *body_rows = rows
    columns = max(len(row) for row in rows)
    first_width = width * (0.46 if columns == 2 else 1.0 / columns)
    widths = [first_width] + [
        (width - first_width) / (columns - 1) for _ in range(columns - 1)
    ]

    data = [[Paragraph(inline(cell), styles["cell_head"]) for cell in header]]
    for row in body_rows:
        padded = row + [""] * (columns - len(row))
        data.append([Paragraph(inline(cell), styles["cell"]) for cell in padded])

    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette.table_header_background)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(palette.border)),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for index in range(1, len(data)):
        if index % 2 == 0:
            style.append(
                ("BACKGROUND", (0, index), (-1, index), colors.HexColor(palette.surface))
            )
    table.setStyle(TableStyle(style))
    return KeepTogether([table, Spacer(1, 11)])


def build_story(blocks: list[Block], styles, palette, width: float) -> list:
    story: list = []
    seen_title = False
    for block in blocks:
        if block.kind == "heading":
            if block.level == 1 and not seen_title:
                seen_title = True
                story.append(Paragraph(inline(block.lines[0]), styles["title"]))
                rule = Table([[""]], colWidths=[width], rowHeights=[2.4])
                rule.setStyle(
                    TableStyle(
                        [
                            (
                                "BACKGROUND",
                                (0, 0),
                                (-1, -1),
                                colors.HexColor(palette.rule_strong),
                            )
                        ]
                    )
                )
                story.extend([Spacer(1, 5), rule, Spacer(1, 14)])
                continue
            key = {1: "h2", 2: "h2", 3: "h3"}.get(block.level, "h4")
            story.append(Paragraph(inline(block.lines[0]), styles[key]))
        elif block.kind == "para":
            story.append(Paragraph(inline(block.lines[0]), styles["body"]))
        elif block.kind == "bullets":
            for item in block.lines:
                story.append(
                    Paragraph(inline(item), styles["bullet"], bulletText="\u2022")
                )
            story.append(Spacer(1, 5))
        elif block.kind == "table":
            story.append(table_flowable(block, styles, palette, width))
        elif block.kind == "code":
            story.append(code_flowable(block, styles, palette, width))
    return story


def make_footer(palette, title: str):
    def draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor(palette.muted))
        baseline = BOTTOM_MARGIN - 22
        canvas.drawString(LEFT_MARGIN, baseline, title)
        canvas.drawRightString(
            doc.pagesize[0] - RIGHT_MARGIN, baseline, str(canvas.getPageNumber())
        )
        canvas.setStrokeColor(colors.HexColor(palette.rule))
        canvas.setLineWidth(0.5)
        canvas.line(
            LEFT_MARGIN,
            baseline + 11,
            doc.pagesize[0] - RIGHT_MARGIN,
            baseline + 11,
        )
        canvas.restoreState()

    return draw


def render(source: Path, destination: Path, theme: str) -> Path:
    palette = palette_for(theme)
    styles = build_styles(palette)
    width = LETTER[0] - LEFT_MARGIN - RIGHT_MARGIN
    blocks = parse_blocks(source.read_text(encoding="utf-8"))
    title = next(
        (block.lines[0] for block in blocks if block.kind == "heading" and block.level == 1),
        source.stem,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(destination),
        pagesize=LETTER,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=title,
        author="Summit",
    )
    footer = make_footer(palette, title)
    document.build(
        build_story(blocks, styles, palette, width),
        onFirstPage=footer,
        onLaterPages=footer,
    )
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="Markdown file to render")
    parser.add_argument("-o", "--output", type=Path, help="Destination PDF path")
    parser.add_argument("--theme", default="light", help="PDF theme id (default: light)")
    args = parser.parse_args(argv)

    source = args.source.resolve()
    if not source.is_file():
        parser.error(f"No such file: {source}")
    destination = args.output or source.with_suffix(".pdf")

    written = render(source, destination.resolve(), args.theme)
    size = written.stat().st_size
    print(f"Wrote {written} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
