"""Deterministic surgery on a finished document's ``##`` sections.

``strip_excluded_sections`` removes the sections a user turned off: the stage
prompts already tell the model to leave them out, and this pass guarantees it
regardless of how well a small model followed that instruction.

``move_sections_to_end`` relocates trailing sections — a meeting's Closing
Assessment — behind everything else, because the model writes them as part of
the overview while the detailed discussion notes are appended afterwards.

A section is the matching heading line and everything under it, including its
``###`` subsections, up to the next ``#`` or ``##`` heading.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


_H2 = re.compile(r"^\s{0,3}##\s+(?P<title>.+?)\s*#*\s*$")
_H1 = re.compile(r"^\s{0,3}#\s+")
_EMPHASIS = re.compile(r"\*\*|__|[*_`]")
_BLANK_RUN = re.compile(r"\n{3,}")


def normalize_heading(text: str) -> str:
    """A comparison key for a heading: emphasis, colons, and case removed."""
    plain = _EMPHASIS.sub("", str(text))
    plain = plain.strip().strip(":").strip()
    return re.sub(r"\s+", " ", plain).casefold()


def strip_excluded_sections(markdown: str, headings: Iterable[str]) -> str:
    """Remove every ``##`` section of ``markdown`` titled by ``headings``."""
    targets = {normalize_heading(item) for item in headings if str(item).strip()}
    if not targets or not markdown.strip():
        return markdown
    kept: list[str] = []
    skipping = False
    for line in markdown.splitlines():
        match = _H2.match(line)
        if match is not None:
            skipping = normalize_heading(match.group("title")) in targets
            if skipping:
                continue
        elif skipping and _H1.match(line):
            skipping = False
        if not skipping:
            kept.append(line)
    return _BLANK_RUN.sub("\n\n", "\n".join(kept)).strip()


def move_sections_to_end(markdown: str, headings: Iterable[str]) -> str:
    """Move every ``##`` section titled by ``headings`` to the document's end.

    Matching sections keep their relative order; everything else keeps its
    place. A document that already ends with the sections comes back unchanged
    in effect, so the pass is safe to apply repeatedly.
    """
    targets = {normalize_heading(item) for item in headings if str(item).strip()}
    if not targets or not markdown.strip():
        return markdown
    kept: list[str] = []
    moved: list[list[str]] = []
    current: list[str] | None = None
    for line in markdown.splitlines():
        match = _H2.match(line)
        if match is not None:
            if normalize_heading(match.group("title")) in targets:
                current = [line]
                moved.append(current)
                continue
            current = None
        elif current is not None and _H1.match(line):
            current = None
        if current is not None:
            current.append(line)
        else:
            kept.append(line)
    if not moved:
        return markdown
    parts = ["\n".join(kept)] + ["\n".join(section) for section in moved]
    joined = "\n\n".join(part.strip() for part in parts if part.strip())
    return _BLANK_RUN.sub("\n\n", joined).strip()
