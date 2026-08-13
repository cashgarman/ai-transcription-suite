from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Sequence


_SPLIT = re.compile(r"\s*(?:[,;/]|&|\band\b)\s*", re.IGNORECASE)
_GENERIC = {
    "everyone",
    "other members",
    "other team members",
    "others",
    "team",
    "team members",
    "the team",
    "unknown",
    "unnamed",
}
# Tag and entity runs must survive untouched so markup is never rewritten.
_OPAQUE = re.compile(r"<[^>]*>|&[a-zA-Z]+;|&#\d+;")
_WORD = re.compile(r"[A-Za-z][A-Za-z'\u2019-]*")
_CAMEL = re.compile(r"[A-Z][a-z]{2,}")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

_MIN_KEY_LENGTH = 3
_MIN_RATIO = 0.86
_MAX_PHRASE_WORDS = 2


def _normalize(text: str) -> str:
    return _NON_ALNUM.sub("", text.lower())


@dataclass(frozen=True)
class ParticipantStyle:
    name: str
    color: str
    keys: tuple[str, ...]


def parse_participants(raw: str) -> list[str]:
    """Split a participants line into individual names, dropping placeholders."""
    names: list[str] = []
    seen: set[str] = set()
    for chunk in _SPLIT.split(raw or ""):
        name = chunk.strip().strip(".").strip()
        if not name or name.lower() in _GENERIC:
            continue
        key = _normalize(name)
        if len(key) < _MIN_KEY_LENGTH or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _keys(name: str) -> tuple[str, ...]:
    keys = {_normalize(name)}
    for part in re.split(r"[\s\-_]+", name):
        keys.add(_normalize(part))
        keys.update(_normalize(camel) for camel in _CAMEL.findall(part))
    return tuple(sorted(key for key in keys if len(key) >= _MIN_KEY_LENGTH))


class ParticipantHighlighter:
    """Marks participant mentions in rendered markup without touching tags."""

    def __init__(self, styles: Sequence[ParticipantStyle] = ()) -> None:
        self._styles = tuple(style for style in styles if style.keys)

    def __bool__(self) -> bool:
        return bool(self._styles)

    @property
    def styles(self) -> tuple[ParticipantStyle, ...]:
        return self._styles

    def color_for(self, text: str) -> str | None:
        return self._match_color(text)

    def apply(self, markup: str, wrap: Callable[[str, str], str]) -> str:
        if not self._styles or not markup:
            return markup
        pieces: list[str] = []
        cursor = 0
        for opaque in _OPAQUE.finditer(markup):
            pieces.append(self._highlight(markup[cursor : opaque.start()], wrap))
            pieces.append(opaque.group(0))
            cursor = opaque.end()
        pieces.append(self._highlight(markup[cursor:], wrap))
        return "".join(pieces)

    def _highlight(self, text: str, wrap: Callable[[str, str], str]) -> str:
        if not text.strip():
            return text
        words = list(_WORD.finditer(text))
        if not words:
            return text
        pieces: list[str] = []
        cursor = 0
        index = 0
        while index < len(words):
            if not words[index].group(0)[0].isupper():
                index += 1
                continue
            match = self._longest_match(text, words, index)
            if match is None:
                index += 1
                continue
            last, color = match
            start = words[index].start()
            end = words[last].end()
            pieces.append(text[cursor:start])
            pieces.append(wrap(text[start:end], color))
            cursor = end
            index = last + 1
        pieces.append(text[cursor:])
        return "".join(pieces)

    def _longest_match(
        self,
        text: str,
        words: list[re.Match[str]],
        index: int,
    ) -> tuple[int, str] | None:
        for span in range(_MAX_PHRASE_WORDS, 0, -1):
            last = index + span - 1
            if last >= len(words):
                continue
            if not self._is_phrase(text, words, index, last):
                continue
            color = self._match_color(text[words[index].start() : words[last].end()])
            if color:
                return last, color
        return None

    def _is_phrase(
        self,
        text: str,
        words: list[re.Match[str]],
        index: int,
        last: int,
    ) -> bool:
        for position in range(index, last):
            if text[words[position].end() : words[position + 1].start()] != " ":
                return False
            if not words[position + 1].group(0)[0].isupper():
                return False
        return True

    def _match_color(self, phrase: str) -> str | None:
        candidate = _normalize(phrase)
        if len(candidate) < _MIN_KEY_LENGTH:
            return None
        best_ratio = 0.0
        best_color: str | None = None
        for style in self._styles:
            for key in style.keys:
                if key == candidate:
                    return style.color
                # A shared first letter keeps unrelated words out of the ramp.
                if key[0] != candidate[0]:
                    continue
                ratio = SequenceMatcher(None, key, candidate).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_color = style.color
        return best_color if best_ratio >= _MIN_RATIO else None


def build_highlighter(
    participants: str,
    colors: Sequence[str],
) -> ParticipantHighlighter:
    if not colors:
        return ParticipantHighlighter()
    styles = [
        ParticipantStyle(name, colors[index % len(colors)], _keys(name))
        for index, name in enumerate(parse_participants(participants))
    ]
    return ParticipantHighlighter(styles)
