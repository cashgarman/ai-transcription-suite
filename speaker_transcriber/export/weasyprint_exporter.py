from __future__ import annotations

import html
from pathlib import Path

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


def weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


def _inline(text: str) -> str:
    escaped = html.escape(text)
    return escaped.replace("\n", "<br/>")


def _block_html(block: Block) -> str:
    if isinstance(block, ParagraphBlock):
        if not block.text.strip():
            return ""
        return f"<p>{_inline(block.text)}</p>"
    if isinstance(block, HeadingBlock):
        level = 3 if block.level >= 3 else 2
        return f"<h{level}>{_inline(block.text)}</h{level}>"
    if isinstance(block, NumberedListBlock):
        items = "".join(f"<li>{_inline(item)}</li>" for item in block.items if item.strip())
        return f"<ol>{items}</ol>" if items else ""
    if isinstance(block, BulletListBlock):
        items = "".join(f"<li>{_inline(item)}</li>" for item in block.items if item.strip())
        return f"<ul>{items}</ul>" if items else ""
    if isinstance(block, ActionTableBlock):
        rows = [
            "<tr><th>Owner</th><th>Action</th><th>Priority</th></tr>"
        ]
        for row in block.rows:
            rows.append(
                "<tr>"
                f"<td>{_inline(row.owner or '—')}</td>"
                f"<td>{_inline(row.action or '—')}</td>"
                f"<td>{_inline(row.priority or '—')}</td>"
                "</tr>"
            )
        return f"<table>{''.join(rows)}</table>"
    if isinstance(block, RiskListBlock):
        parts: list[str] = []
        for item in block.items:
            if item.text.strip():
                parts.append(f"<p class='risk'>{_inline(item.text)}</p>")
            if item.mitigation.strip():
                parts.append(
                    f"<p class='mitigation'><strong>Mitigation:</strong> "
                    f"{_inline(item.mitigation)}</p>"
                )
        return "".join(parts)
    return ""


def _section_html(section: Section) -> str:
    parts: list[str] = []
    if section.title.strip():
        parts.append(f"<h2>{_inline(section.title)}</h2>")
    for block in section.blocks:
        parts.append(_block_html(block))
    return "".join(parts)


def meeting_document_html(document: MeetingDocument) -> str:
    body: list[str] = []
    if document.title.strip():
        body.append(f"<h1>{_inline(document.title)}</h1>")
    if document.subtitle.strip():
        body.append(f"<p class='subtitle'>{_inline(document.subtitle)}</p>")
    if document.participants.strip():
        body.append(
            f"<p class='meta'><strong>Participants:</strong> "
            f"{_inline(document.participants)}</p>"
        )
    if document.primary_topics.strip():
        body.append(
            f"<p class='meta'><strong>Primary topics:</strong> "
            f"{_inline(document.primary_topics)}</p>"
        )
    for section in document.sections:
        body.append(_section_html(section))
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>{html.escape(document.title or "Meeting notes")}</title>
<style>
  @page {{ size: letter; margin: 0.85in 0.9in; }}
  body {{ font-family: "Times New Roman", Times, serif; font-size: 11pt; color: #222; }}
  h1 {{ font-size: 18pt; margin: 0 0 8pt 0; }}
  h2 {{ font-size: 13pt; margin: 16pt 0 8pt 0; }}
  h3 {{ font-size: 12pt; margin: 12pt 0 6pt 0; }}
  .subtitle, .meta {{ color: #444; margin: 0 0 8pt 0; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8pt 0 12pt 0; }}
  th, td {{ border: 0.4pt solid #8c8c8c; padding: 5pt 6pt; vertical-align: top; }}
  th {{ background: #ededed; text-align: left; }}
  .risk {{ margin-bottom: 2pt; }}
  .mitigation {{ margin: 0 0 10pt 0; }}
</style>
</head>
<body>
{''.join(body)}
</body>
</html>
"""


def export_weasyprint_pdf(document: MeetingDocument, path: Path) -> None:
    if not weasyprint_available():
        raise RuntimeError(
            "WeasyPrint is not available. Install it and its native libraries "
            "(Pango/Cairo/GTK), or switch Format PDF notes to ReportLab."
        )
    from weasyprint import HTML

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=meeting_document_html(document)).write_pdf(str(destination))
