from __future__ import annotations

import html
import os
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
from speaker_transcriber.export.participants import (
    ParticipantHighlighter,
    build_highlighter,
)
from speaker_transcriber.export.pdf_theme import (
    anchor_map,
    normalize_theme,
    palette_for,
    should_render_toc,
    toc_entries,
)


_GOBJECT_DLL = "libgobject-2.0-0.dll"
_DEFAULT_DLL_DIRS = (
    Path(r"C:\msys64\ucrt64\bin"),
    Path(r"C:\msys64\mingw64\bin"),
    Path(r"C:\Program Files\GTK3-Runtime Win64\bin"),
)


def configure_weasyprint_libraries() -> list[str]:
    existing = [
        part.strip()
        for part in os.environ.get("WEASYPRINT_DLL_DIRECTORIES", "").split(os.pathsep)
        if part.strip()
    ]
    discovered = [
        str(path)
        for path in _DEFAULT_DLL_DIRS
        if (path / _GOBJECT_DLL).is_file() and str(path) not in existing
    ]
    combined = existing + discovered
    if combined:
        os.environ["WEASYPRINT_DLL_DIRECTORIES"] = os.pathsep.join(combined)
    return combined


def weasyprint_available() -> bool:
    configure_weasyprint_libraries()
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


def _inline(text: str) -> str:
    escaped = html.escape(text)
    return escaped.replace("\n", "<br/>")


def _wrap_participant(text: str, color: str) -> str:
    return f"<strong class='participant' style='color:{color}'>{text}</strong>"


def _rich(text: str, highlighter: ParticipantHighlighter) -> str:
    return highlighter.apply(_inline(text), _wrap_participant)


def _block_html(
    block: Block,
    anchor: str = "",
    highlighter: ParticipantHighlighter | None = None,
) -> str:
    highlighter = highlighter or ParticipantHighlighter()
    if isinstance(block, ParagraphBlock):
        if not block.text.strip():
            return ""
        return f"<p>{_rich(block.text, highlighter)}</p>"
    if isinstance(block, HeadingBlock):
        level = 3 if block.level >= 3 else 2
        attribute = f' id="{html.escape(anchor)}"' if anchor else ""
        return f"<h{level}{attribute}>{_inline(block.text)}</h{level}>"
    if isinstance(block, NumberedListBlock):
        items = "".join(
            f"<li>{_rich(item, highlighter)}</li>"
            for item in block.items
            if item.strip()
        )
        return f"<ol>{items}</ol>" if items else ""
    if isinstance(block, BulletListBlock):
        items = "".join(
            f"<li>{_rich(item, highlighter)}</li>"
            for item in block.items
            if item.strip()
        )
        return f"<ul>{items}</ul>" if items else ""
    if isinstance(block, ActionTableBlock):
        rows = [
            "<tr><th>Owner</th><th>Action</th><th>Priority</th></tr>"
        ]
        for row in block.rows:
            rows.append(
                "<tr>"
                f"<td>{_rich(row.owner or '—', highlighter)}</td>"
                f"<td>{_rich(row.action or '—', highlighter)}</td>"
                f"<td>{_inline(row.priority or '—')}</td>"
                "</tr>"
            )
        return f"<table>{''.join(rows)}</table>"
    if isinstance(block, RiskListBlock):
        parts: list[str] = []
        for item in block.items:
            if not item.text.strip() and not item.mitigation.strip():
                continue
            card: list[str] = ["<div class='risk-card'>"]
            if item.text.strip():
                card.append(f"<p class='risk'>{_rich(item.text, highlighter)}</p>")
            if item.mitigation.strip():
                card.append(
                    f"<p class='mitigation'><strong>Mitigation:</strong> "
                    f"{_rich(item.mitigation, highlighter)}</p>"
                )
            card.append("</div>")
            parts.append("".join(card))
        return "".join(parts)
    return ""


def _section_html(
    section: Section,
    section_index: int,
    anchors: dict[tuple[int, int | None], str],
    with_divider: bool,
    highlighter: ParticipantHighlighter | None = None,
) -> str:
    highlighter = highlighter or ParticipantHighlighter()
    parts: list[str] = []
    classes = "section divided" if with_divider else "section"
    parts.append(f"<section class='{classes}'>")
    if section.title.strip():
        anchor = anchors.get((section_index, None), "")
        attribute = f' id="{html.escape(anchor)}"' if anchor else ""
        parts.append(f"<h2{attribute}>{_inline(section.title)}</h2>")
    for block_index, block in enumerate(section.blocks):
        parts.append(
            _block_html(
                block,
                anchors.get((section_index, block_index), ""),
                highlighter,
            )
        )
    parts.append("</section>")
    return "".join(parts)


def _toc_html(document: MeetingDocument) -> str:
    if not should_render_toc(document):
        return ""
    entries = toc_entries(document)
    if not entries:
        return ""
    items = "".join(
        f"<li class='toc-level-{entry.level}'>"
        f"<a href='#{html.escape(entry.anchor)}'>{_inline(entry.title)}</a>"
        "</li>"
        for entry in entries
    )
    return (
        "<nav class='toc'><p class='toc-title'>Contents</p>"
        f"<ul>{items}</ul></nav>"
    )


def meeting_document_html(document: MeetingDocument, theme: str = "light") -> str:
    theme = normalize_theme(theme)
    anchors = anchor_map(document)
    highlighter = build_highlighter(
        document.participants,
        palette_for(theme).participants,
    )
    header: list[str] = []
    if document.title.strip():
        header.append(f"<h1>{_inline(document.title)}</h1>")
    if document.subtitle.strip():
        header.append(f"<p class='subtitle'>{_inline(document.subtitle)}</p>")
    if document.participants.strip():
        header.append(
            f"<p class='meta'><strong>Participants:</strong> "
            f"{_rich(document.participants, highlighter)}</p>"
        )
    if document.primary_topics.strip():
        header.append(
            f"<p class='meta'><strong>Primary topics:</strong> "
            f"{_inline(document.primary_topics)}</p>"
        )
    body: list[str] = []
    if header:
        body.append(f"<header class='doc-header'>{''.join(header)}</header>")
    body.append(_toc_html(document))
    divider_pending = False
    for index, section in enumerate(document.sections):
        body.append(
            _section_html(section, index, anchors, divider_pending, highlighter)
        )
        divider_pending = True
    running_title = html.escape(document.title.strip() or "Meeting notes")
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>{html.escape(document.title or "Meeting notes")}</title>
<style>
{_stylesheet(theme, running_title)}
</style>
</head>
<body class="theme-{theme}">
{''.join(body)}
</body>
</html>
"""


def _stylesheet(theme: str, running_title: str) -> str:
    palette = palette_for(theme)
    return f"""  @page {{
    size: letter;
    margin: 1in 0.9in 0.85in 0.9in;
    background: {palette.page};
    @top-left {{
      content: "{running_title}";
      font-family: "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 8.5pt;
      color: {palette.muted};
    }}
    @bottom-right {{
      content: counter(page) " of " counter(pages);
      font-family: "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 8.5pt;
      color: {palette.muted};
    }}
  }}
  body {{
    font-family: "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.5;
    color: {palette.text};
    background: {palette.page};
    margin: 0;
  }}
  h1 {{ font-size: 21pt; line-height: 1.2; margin: 0 0 6pt 0; color: {palette.heading}; }}
  h2 {{
    font-size: 14pt;
    margin: 6pt 0 8pt 0;
    color: {palette.heading};
  }}
  h3 {{ font-size: 11.5pt; margin: 12pt 0 5pt 0; color: {palette.text}; }}
  a {{ color: {palette.accent}; text-decoration: none; }}
  .subtitle {{ color: {palette.muted}; font-style: italic; margin: 0 0 10pt 0; }}
  .meta {{ color: {palette.muted}; font-size: 9.5pt; margin: 0 0 3pt 0; }}
  .doc-header {{
    border-bottom: 1.2pt solid {palette.rule_strong};
    padding-bottom: 10pt;
    margin-bottom: 14pt;
  }}
  .toc {{
    background: {palette.surface};
    border: 0.6pt solid {palette.border};
    border-radius: 3pt;
    padding: 10pt 12pt;
    margin: 0 0 6pt 0;
  }}
  .toc-title {{
    font-weight: 700;
    font-size: 10pt;
    color: {palette.heading};
    margin: 0 0 6pt 0;
  }}
  .toc ul {{ list-style: none; margin: 0; padding: 0; }}
  .toc li {{ margin: 0; line-height: 1.5; }}
  .toc-level-2 {{ padding-left: 14pt; font-size: 9.5pt; }}
  .toc-level-2 a {{ color: {palette.muted}; }}
  .section {{ padding-top: 4pt; }}
  .section.divided {{
    border-top: 0.7pt solid {palette.rule};
    margin-top: 14pt;
    padding-top: 12pt;
  }}
  ul, ol {{ margin: 0 0 10pt 0; padding-left: 18pt; }}
  li {{ margin-bottom: 5pt; }}
  li::marker {{ color: {palette.accent}; font-weight: 700; }}
  table {{ width: 100%; border-collapse: collapse; margin: 8pt 0 12pt 0; }}
  td {{
    padding: 7pt 8pt;
    vertical-align: top;
    border-bottom: 0.5pt solid {palette.border};
  }}
  th {{
    padding: 7pt 8pt;
    text-align: left;
    background: {palette.table_header_background};
    color: {palette.table_header_text};
    font-size: 9.5pt;
  }}
  tr:nth-child(odd) td {{ background: {palette.surface}; }}
  .risk-card {{
    background: {palette.surface};
    border-left: 2.5pt solid {palette.accent};
    padding: 8pt 10pt;
    margin: 0 0 8pt 0;
  }}
  .participant {{ font-weight: 700; }}
  .risk {{ font-weight: 700; margin: 0 0 3pt 0; }}
  .mitigation {{ color: {palette.muted}; font-size: 10pt; margin: 0; }}"""


def export_weasyprint_pdf(
    document: MeetingDocument,
    path: Path,
    theme: str = "light",
) -> None:
    if not weasyprint_available():
        raise RuntimeError(
            "WeasyPrint is not available. Install it and its native libraries "
            "(Pango/Cairo/GTK), or switch Format PDF notes to ReportLab."
        )
    from weasyprint import HTML

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=meeting_document_html(document, theme=theme)).write_pdf(
        str(destination)
    )
