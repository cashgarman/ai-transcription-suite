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
    as_script,
    split_turn,
)
from speaker_transcriber.export.participants import (
    ParticipantHighlighter,
    build_highlighter,
)
from speaker_transcriber.export.pdf_layout import (
    COMPACT,
    COVER,
    MASTHEAD,
    PLAIN,
    PdfLayout,
    layout_for,
)
from speaker_transcriber.export.pdf_options import apply_pdf_options
from speaker_transcriber.export.pdf_theme import (
    PdfPalette,
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


class _TurnColors:
    """One colour per voice in a script, assigned in order of first appearance."""

    def __init__(self, palette: PdfPalette) -> None:
        self._palette = palette
        self._assigned: dict[str, str] = {}

    def color_for(self, speaker: str) -> str:
        key = speaker.strip().lower()
        if key not in self._assigned:
            available = self._palette.participants or (self._palette.accent,)
            self._assigned[key] = available[len(self._assigned) % len(available)]
        return self._assigned[key]

    def speakers_in(self, document: MeetingDocument) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for section in document.sections:
            for block in section.blocks:
                if not isinstance(block, ParagraphBlock):
                    continue
                turn = split_turn(block.text)
                if turn is None or turn[0].lower() in seen:
                    continue
                seen.add(turn[0].lower())
                found.append(turn[0])
                self.color_for(turn[0])
        return found


def _turn_html(text: str, turns: _TurnColors, highlighter: ParticipantHighlighter) -> str:
    turn = split_turn(text)
    if turn is None:
        return f"<p>{_rich(text, highlighter)}</p>"
    speaker, spoken = turn
    color = turns.color_for(speaker)
    return (
        "<p class='line'>"
        f"<span class='host' style='color:{color}'>{_inline(speaker)}</span>"
        f"{_inline(spoken)}</p>"
    )


def _block_html(
    block: Block,
    anchor: str = "",
    highlighter: ParticipantHighlighter | None = None,
    layout: PdfLayout | None = None,
    turns: _TurnColors | None = None,
) -> str:
    highlighter = highlighter or ParticipantHighlighter()
    if isinstance(block, ParagraphBlock):
        if not block.text.strip():
            return ""
        if layout is not None and layout.speaker_turns and turns is not None:
            return _turn_html(block.text, turns, highlighter)
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
    layout: PdfLayout | None = None,
    turns: _TurnColors | None = None,
) -> str:
    highlighter = highlighter or ParticipantHighlighter()
    parts: list[str] = []
    classes = "section divided" if with_divider else "section"
    parts.append(f"<section class='{classes}'>")
    if section.title.strip():
        anchor = anchors.get((section_index, None), "")
        attribute = f' id="{html.escape(anchor)}"' if anchor else ""
        parts.append(f"<h2{attribute}>{_inline(section.title)}</h2>")
    cards = bool(layout and layout.person_cards) and any(
        isinstance(block, HeadingBlock) and block.level >= 3
        for block in section.blocks
    )
    open_card = False
    for block_index, block in enumerate(section.blocks):
        rendered = _block_html(
            block,
            anchors.get((section_index, block_index), ""),
            highlighter,
            layout,
            turns,
        )
        if cards and isinstance(block, HeadingBlock) and block.level >= 3:
            if open_card:
                parts.append("</div>")
            parts.append("<div class='person-card'>")
            open_card = True
        parts.append(rendered)
    if open_card:
        parts.append("</div>")
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


def _front_matter_html(
    document: MeetingDocument,
    layout: PdfLayout,
    highlighter: ParticipantHighlighter,
    turns: _TurnColors,
) -> str:
    if layout.front_matter == PLAIN:
        return ""
    title = document.title.strip() or layout.fallback_title
    if layout.front_matter == MASTHEAD:
        lede = (
            f"<p class='lede'>{_inline(document.subtitle)}</p>"
            if document.subtitle.strip()
            else ""
        )
        return (
            "<header class='masthead'>"
            f"<p class='kicker'>{_inline(layout.kicker.upper())}</p>"
            f"<h1>{_inline(title)}</h1>"
            f"</header>{lede}"
        )

    parts: list[str] = []
    if layout.kicker:
        parts.append(f"<p class='kicker'>{_inline(layout.kicker.upper())}</p>")
    parts.append(f"<h1>{_inline(title)}</h1>")
    if document.subtitle.strip():
        parts.append(f"<p class='subtitle'>{_inline(document.subtitle)}</p>")
    if layout.show_participants and document.participants.strip():
        parts.append(
            f"<p class='meta'><strong>Participants:</strong> "
            f"{_rich(document.participants, highlighter)}</p>"
        )
    if layout.show_participants and document.primary_topics.strip():
        parts.append(
            f"<p class='meta'><strong>Primary topics:</strong> "
            f"{_inline(document.primary_topics)}</p>"
        )
    speakers = turns.speakers_in(document)
    if len(speakers) >= 2:
        legend = " · ".join(
            f"<span class='host' style='color:{turns.color_for(name)}'>"
            f"{_inline(name)}</span>"
            for name in speakers[:4]
        )
        parts.append(f"<p class='legend'>{legend}</p>")
    css_class = "cover" if layout.front_matter == COVER else "doc-header compact"
    return f"<header class='{css_class}'>{''.join(parts)}</header>"


def meeting_document_html(
    document: MeetingDocument,
    theme: str = "light",
    style: str | None = None,
    options: dict[str, bool] | None = None,
) -> str:
    theme = normalize_theme(theme)
    layout = apply_pdf_options(layout_for(style), options)
    palette = palette_for(theme, style)
    if layout.speaker_turns:
        document = as_script(document)
    anchors = anchor_map(document)
    highlighter = build_highlighter(document.participants, palette.participants)
    turns = _TurnColors(palette)

    body: list[str] = [_front_matter_html(document, layout, highlighter, turns)]
    if layout.show_toc:
        body.append(_toc_html(document))
    divider_pending = False
    for index, section in enumerate(document.sections):
        body.append(
            _section_html(
                section,
                index,
                anchors,
                divider_pending and not layout.slide_per_section,
                highlighter,
                layout,
                turns,
            )
        )
        divider_pending = True
    running_title = html.escape(
        "" if layout.front_matter == MASTHEAD else document.title.strip()
    )
    title = document.title.strip() or layout.fallback_title
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>{html.escape(title)}</title>
<style>
{_stylesheet(theme, running_title, layout, style)}
</style>
</head>
<body class="theme-{theme} layout-{layout.kind}">
{''.join(body)}
</body>
</html>
"""


def _stylesheet(
    theme: str,
    running_title: str,
    layout: PdfLayout | None = None,
    style: str | None = None,
) -> str:
    layout = layout or layout_for(style)
    palette = palette_for(theme, style)
    page_size = "letter landscape" if layout.landscape else "letter"
    page_number = (
        f'"{layout.footer_label} " counter(page)'
        if layout.footer_label
        else 'counter(page) " of " counter(pages)'
    )
    return f"""  @page {{
    size: {page_size};
    margin: 1in 0.9in 0.85in 0.9in;
    background: {palette.page};
    @top-left {{
      content: "{running_title}";
      font-family: "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 8.5pt;
      color: {palette.muted};
    }}
    @bottom-right {{
      content: {page_number};
      font-family: "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 8.5pt;
      color: {palette.muted};
    }}
  }}
{_layout_page_rules(layout)}
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
  .mitigation {{ color: {palette.muted}; font-size: 10pt; margin: 0; }}
  .kicker {{
    font-weight: 700;
    font-size: 9.5pt;
    letter-spacing: 0.08em;
    color: {palette.accent};
    margin: 0 0 10pt 0;
  }}
  .cover {{
    padding-top: 1.6in;
    break-after: page;
    border-bottom: none;
  }}
  .cover h1 {{ font-size: 30pt; line-height: 1.15; margin-bottom: 12pt; }}
  .cover .subtitle {{ font-size: 14pt; margin-bottom: 18pt; }}
  .compact {{ padding-bottom: 8pt; }}
  .masthead {{
    background: {palette.table_header_background};
    color: {palette.table_header_text};
    padding: 14pt 14pt 16pt 14pt;
    margin-bottom: 4pt;
  }}
  .masthead .kicker {{ color: {palette.table_header_text}; margin-bottom: 6pt; }}
  .masthead h1 {{ color: {palette.table_header_text}; font-size: 25pt; margin: 0; }}
  .lede {{
    font-style: italic;
    font-size: 13pt;
    margin: 10pt 0 12pt 0;
    padding-bottom: 10pt;
    border-bottom: 1.2pt solid {palette.rule_strong};
  }}
  .legend {{ font-size: 9.5pt; margin: 6pt 0 0 0; }}
  .host {{ font-weight: 700; }}
  .line {{ padding-left: 54pt; text-indent: -54pt; margin: 0 0 7pt 0; }}
  .line .host {{ padding-right: 10pt; }}
  .person-card {{
    background: {palette.surface};
    border-left: 2.5pt solid {palette.accent};
    padding: 8pt 10pt;
    margin: 0 0 8pt 0;
    break-inside: avoid;
  }}
  .person-card h3 {{ margin-top: 0; color: {palette.heading}; }}"""


def _layout_page_rules(layout: PdfLayout) -> str:
    """Page rules that only some layouts need: bare covers and slide breaks."""
    rules: list[str] = []
    if layout.front_matter in (COVER, MASTHEAD):
        rules.append(
            "  @page :first {\n"
            '    @top-left { content: ""; }\n'
            '    @bottom-right { content: ""; }\n'
            "  }"
        )
    if layout.slide_per_section:
        rules.append("  .section { break-before: page; }")
        rules.append("  .section:first-of-type { counter-reset: page 1; }")
        rules.append("  .section h2 { font-size: 26pt; margin-bottom: 16pt; }")
        rules.append("  .section li { font-size: 14pt; margin-bottom: 10pt; }")
    return "\n".join(rules)


def export_weasyprint_pdf(
    document: MeetingDocument,
    path: Path,
    theme: str = "light",
    style: str | None = None,
    options: dict[str, bool] | None = None,
) -> None:
    if not weasyprint_available():
        raise RuntimeError(
            "WeasyPrint is not available. Install it and its native libraries "
            "(Pango/Cairo/GTK), or switch Format PDF notes to ReportLab."
        )
    from weasyprint import HTML

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    html_text = meeting_document_html(
        document,
        theme=theme,
        style=style,
        options=options,
    )
    HTML(string=html_text).write_pdf(str(destination))
