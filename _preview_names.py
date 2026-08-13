"""Temporary visual check for participant colour coding."""
from pathlib import Path

import pypdfium2 as pdfium

from speaker_transcriber.export.meeting_document import parse_meeting_markdown
from speaker_transcriber.export.pdf_exporter import export_meeting_pdf


markdown = """# Development Sync and Replay System Review

*The team reviewed branching, the replay system, and procedural generation.*

**Participants:** Cash, GranSeba, Brian, Andrew, Sergio

**Primary topics:** Branching, replay system, movement, procedural generation

## Executive Summary

Cash mentioned reworking how the time slowdown works, noting that they were
originally using an asset framework. GranSeba stated they did not use an asset
framework, and Brian responded in a sub-chat.

## Key Decisions and Direction

- Cash explained that Sergio wanted to optimize the path into a traditional
  animation sequence, whereas Cash's current rework involves moving cell by cell.
- GranSeba asked which branch Cash's current work was on.
- Gran Seba eventually navigated to the "new time logic" branch.
- Andrew described a music background and a current focus on sound-design work.
- Case studies were reviewed on Tuesday by the whole team.

## Action Items

| Owner | Action | Priority |
| --- | --- | --- |
| Cash | Fix boss locomotion in the movement system | High |
| GranSeba | Redo the ability system design with Brian | Medium |
| Andrew | Continue sound integration work | Low |

## Risks, Dependencies, and Blockers

Wildfire situation in BC: Impacts Cash's consistent availability.

Mitigation: GranSeba covers the ability designer work meanwhile.

## Closing Assessment

The team achieved strong alignment on immediate development priorities.
"""

out = Path("_preview")
out.mkdir(exist_ok=True)
for theme in ("light", "dark"):
    document = parse_meeting_markdown(markdown)
    path = out / f"names_{theme}.pdf"
    export_meeting_pdf(document, path, theme=theme)
    pdf = pdfium.PdfDocument(str(path))
    for index in range(len(pdf)):
        pdf[index].render(scale=2).to_pil().save(out / f"names_{theme}_{index + 1}.png")
    print(theme, "pages:", len(pdf))
