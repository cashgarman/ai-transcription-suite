from __future__ import annotations

import re
from dataclasses import dataclass, field


_FENCE_OPEN = re.compile(r"^```[a-zA-Z0-9_-]*\s*$")
_ATX_H1 = re.compile(r"^#\s+(.+)$")
_ATX_H2 = re.compile(r"^##\s+(.+)$")
_ATX_H3 = re.compile(r"^###\s+(.+)$")
_BOLD_LINE = re.compile(r"^(?:\*\*|__)(.+?)(?:\*\*|__)\s*$")
_ITALIC_LINE = re.compile(r"^(?:\*|_)(.+?)(?:\*|_)\s*$")
_META_LINE = re.compile(
    r"^(?:\*\*|__)?(participants|primary topics)"
    r"(?::(?:\*\*|__)?|(?:\*\*|__)?\s*[:—–-])\s*(.*)$",
    re.IGNORECASE,
)
_META_LABEL = re.compile(
    r"^(?:\*\*|__)?(participants|primary topics)(?:\*\*|__)?\s*$",
    re.IGNORECASE,
)
_NUMBERED = re.compile(r"^(\d+)[.)]\s+(.*)$")
_BULLET = re.compile(r"^[-*+]\s+(.*)$")
_TABLE_SEP = re.compile(r"^[\s|:-]+$")
_INLINE_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_INLINE_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_PLACEHOLDER = re.compile(r"optional local ollama summary", re.IGNORECASE)
_BOLD_TURN = re.compile(r"^\*\*\s*([^*\n]{1,40}?)\s*:?\s*\*\*\s*:?\s*(.*)$", re.DOTALL)
_PLAIN_TURN = re.compile(r"^([^*:\n]{1,40}?)\s*:\s*(.+)$", re.DOTALL)

_KNOWN_SECTIONS = (
    "executive summary",
    "key decisions and direction",
    "key decisions",
    "action items",
    "open questions",
    "risks, dependencies, and blockers",
    "risks and dependencies",
    "risks",
    "closing assessment",
)


@dataclass
class ActionItem:
    owner: str = ""
    action: str = ""
    priority: str = ""

    def is_usable(self) -> bool:
        return bool(self.owner.strip() or self.action.strip())


@dataclass
class RiskItem:
    text: str
    mitigation: str = ""


@dataclass
class ParagraphBlock:
    text: str


@dataclass
class HeadingBlock:
    text: str
    level: int = 3


@dataclass
class NumberedListBlock:
    items: list[str]


@dataclass
class BulletListBlock:
    items: list[str]


@dataclass
class ActionTableBlock:
    rows: list[ActionItem]


@dataclass
class RiskListBlock:
    items: list[RiskItem]


Block = (
    ParagraphBlock
    | HeadingBlock
    | NumberedListBlock
    | BulletListBlock
    | ActionTableBlock
    | RiskListBlock
)


@dataclass
class Section:
    title: str
    blocks: list[Block] = field(default_factory=list)


@dataclass
class MeetingDocument:
    title: str = ""
    subtitle: str = ""
    participants: str = ""
    primary_topics: str = ""
    sections: list[Section] = field(default_factory=list)

    def named_sections(self) -> list[Section]:
        return [section for section in self.sections if section.title.strip()]

    def has_action_table(self) -> bool:
        for section in self.sections:
            for block in section.blocks:
                if isinstance(block, ActionTableBlock) and any(
                    row.is_usable() for row in block.rows
                ):
                    return True
        return False

    def needs_format_pass(self, require_action_table: bool = True) -> bool:
        return not (
            bool(self.title.strip())
            and bool(self.named_sections())
            and (self.has_action_table() or not require_action_table)
        )


def is_usable_summary_markdown(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if lowered.startswith("generating summary"):
        return False
    if lowered.startswith("summary failed"):
        return False
    if _PLACEHOLDER.search(stripped):
        return False
    return True


def strip_inline_markdown(text: str) -> str:
    cleaned = text.strip()
    cleaned = _INLINE_BOLD.sub(lambda match: match.group(1) or match.group(2) or "", cleaned)
    cleaned = _INLINE_CODE.sub(r"\1", cleaned)
    cleaned = _INLINE_ITALIC.sub(
        lambda match: match.group(1) or match.group(2) or "",
        cleaned,
    )
    return cleaned.strip()


def parse_meeting_markdown(text: str) -> MeetingDocument:
    lines = _strip_fence(text).splitlines()
    index = _skip_blank(lines, 0)
    title, index = _consume_title(lines, index)
    index = _skip_blank(lines, index)
    subtitle, index = _consume_subtitle(lines, index)

    participants = ""
    primary_topics = ""
    sections: list[Section] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        body = current_lines
        current_lines = []
        if current_title is None:
            if _has_content(body):
                sections.append(Section("", parse_section_blocks(body, "")))
            return
        sections.append(
            Section(current_title, parse_section_blocks(body, current_title))
        )

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if current_title is None:
            meta_key, meta_value, index = _consume_metadata(lines, index)
            if meta_key is not None:
                value = strip_inline_markdown(meta_value)
                if meta_key == "participants":
                    participants = value
                else:
                    primary_topics = value
                continue
        header = _match_major_header(stripped)
        if header is not None:
            flush()
            current_title = header
            index += 1
            continue
        current_lines.append(raw)
        index += 1
    flush()

    return MeetingDocument(
        title=title,
        subtitle=subtitle,
        participants=participants,
        primary_topics=primary_topics,
        sections=sections,
    )


def split_turn(text: str) -> tuple[str, str] | None:
    """A script line split into who spoke and what they said, if it is one."""
    stripped = text.strip()
    for pattern in (_BOLD_TURN, _PLAIN_TURN):
        match = pattern.match(stripped)
        if match is None:
            continue
        speaker = match.group(1).strip()
        if speaker:
            return speaker, match.group(2).strip()
    return None


def as_script(document: MeetingDocument) -> MeetingDocument:
    """Give a script back its opening lines.

    A transcript or dialogue has no title, so the parser reads the first spoken
    line as one. For those styles the line belongs in the body instead.
    """
    spoken = [
        text.strip()
        for text in (document.title, document.subtitle)
        if text.strip() and split_turn(text) is not None
    ]
    if not spoken:
        return document
    blocks: list[Block] = [ParagraphBlock(text) for text in spoken]
    sections = list(document.sections)
    if sections and not sections[0].title.strip():
        sections[0] = Section(sections[0].title, blocks + sections[0].blocks)
    else:
        sections.insert(0, Section("", blocks))
    return MeetingDocument(
        title="" if split_turn(document.title) is not None else document.title,
        subtitle="" if split_turn(document.subtitle) is not None else document.subtitle,
        participants=document.participants,
        primary_topics=document.primary_topics,
        sections=sections,
    )


def parse_section_blocks(lines: list[str], section_title: str) -> list[Block]:
    blocks: list[Block] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        if _is_table_row(lines[index]):
            table, index = _consume_table(lines, index)
            if table is not None:
                blocks.append(table)
                continue
        numbered = _NUMBERED.match(lines[index].strip())
        if numbered:
            items, index = _consume_list(lines, index, _NUMBERED)
            blocks.append(NumberedListBlock(items))
            continue
        bullet = _BULLET.match(lines[index].strip())
        if bullet:
            items, index = _consume_list(lines, index, _BULLET)
            blocks.append(BulletListBlock(items))
            continue
        heading = _ATX_H3.match(lines[index].strip())
        if heading:
            blocks.append(HeadingBlock(strip_inline_markdown(heading.group(1)), 3))
            index += 1
            continue
        paragraph, index = _consume_paragraph(lines, index)
        if paragraph:
            blocks.append(ParagraphBlock(paragraph))
            continue
        leftover = lines[index].strip()
        nested = _ATX_H2.match(leftover)
        if nested:
            blocks.append(HeadingBlock(strip_inline_markdown(nested.group(1)), 2))
        elif leftover:
            blocks.append(ParagraphBlock(strip_inline_markdown(leftover)))
        index += 1
    if "risk" in section_title.lower():
        return _group_risks(blocks)
    return blocks


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and (
        _FENCE_OPEN.match(lines[0].strip()) or lines[0].strip() == "```"
    ):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _skip_blank(lines: list[str], index: int) -> int:
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def _has_content(lines: list[str]) -> bool:
    return any(line.strip() for line in lines)


def _consume_title(lines: list[str], index: int) -> tuple[str, int]:
    if index >= len(lines):
        return "", index
    stripped = lines[index].strip()
    heading = _ATX_H1.match(stripped)
    if heading:
        return strip_inline_markdown(heading.group(1)), index + 1
    if (
        not _match_major_header(stripped)
        and _META_LINE.match(stripped) is None
        and _META_LABEL.match(stripped) is None
        and not _is_table_row(stripped)
        and _NUMBERED.match(stripped) is None
        and _BULLET.match(stripped) is None
    ):
        return strip_inline_markdown(stripped), index + 1
    return "", index


def _consume_subtitle(lines: list[str], index: int) -> tuple[str, int]:
    if index >= len(lines):
        return "", index
    stripped = lines[index].strip()
    if _match_major_header(stripped) or _is_table_row(stripped):
        return "", index
    if _META_LINE.match(stripped) or _META_LABEL.match(stripped):
        return "", index
    italic = _ITALIC_LINE.match(stripped)
    if italic:
        return strip_inline_markdown(italic.group(1)), index + 1
    if stripped.lower().startswith("meeting summary"):
        return strip_inline_markdown(stripped), index + 1
    return "", index


def _consume_metadata(
    lines: list[str],
    index: int,
) -> tuple[str | None, str, int]:
    if index >= len(lines):
        return None, "", index
    stripped = lines[index].strip()
    labeled = _META_LINE.match(stripped)
    if labeled:
        value = labeled.group(2).strip()
        key = labeled.group(1).lower()
        index += 1
        if value:
            return key, value, index
        collected: list[str] = []
        while index < len(lines):
            continuation = lines[index].strip()
            if not continuation:
                break
            if _match_major_header(continuation) or _META_LINE.match(continuation):
                break
            if _META_LABEL.match(continuation):
                break
            collected.append(continuation)
            index += 1
        return key, " ".join(collected), index
    label_only = _META_LABEL.match(stripped)
    if label_only:
        index += 1
        collected: list[str] = []
        while index < len(lines):
            continuation = lines[index].strip()
            if not continuation:
                break
            if _match_major_header(continuation) or _META_LINE.match(continuation):
                break
            if _META_LABEL.match(continuation):
                break
            collected.append(continuation)
            index += 1
        return label_only.group(1).lower(), " ".join(collected), index
    return None, "", index


def _match_major_header(stripped: str) -> str | None:
    heading = _ATX_H2.match(stripped)
    if heading:
        return strip_inline_markdown(heading.group(1))
    bold = _BOLD_LINE.match(stripped)
    if bold:
        title = strip_inline_markdown(bold.group(1))
        if _is_known_section(title):
            return title
    if _is_known_section(stripped):
        return strip_inline_markdown(stripped)
    return None


def _is_known_section(title: str) -> bool:
    normalized = strip_inline_markdown(title).lower().rstrip(":")
    return normalized in _KNOWN_SECTIONS or normalized.startswith("risks")


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _starts_new_block(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if _is_table_row(stripped):
        return True
    if _ATX_H2.match(stripped) or _ATX_H3.match(stripped):
        return True
    if _NUMBERED.match(stripped) or _BULLET.match(stripped):
        return True
    if _match_major_header(stripped):
        return True
    return False


def _consume_table(
    lines: list[str],
    index: int,
) -> tuple[ActionTableBlock | None, int]:
    rows: list[list[str]] = []
    cursor = index
    while cursor < len(lines) and _is_table_row(lines[cursor]):
        rows.append(_split_table_row(lines[cursor]))
        cursor += 1
    body = [row for row in rows if not _is_separator_row(row)]
    if len(body) < 2:
        return None, index + 1
    header = [cell.lower() for cell in body[0]]
    owner_index = _column_index(header, ("owner", "owners"))
    action_index = _column_index(header, ("action", "task", "item"))
    priority_index = _column_index(header, ("priority", "pri"))
    items: list[ActionItem] = []
    for row in body[1:]:
        items.append(
            ActionItem(
                owner=_cell(row, owner_index if owner_index is not None else 0),
                action=_cell(
                    row,
                    action_index if action_index is not None else 1,
                ),
                priority=_cell(
                    row,
                    priority_index if priority_index is not None else 2,
                ),
            )
        )
    if not any(item.is_usable() for item in items):
        return None, index + 1
    return ActionTableBlock(items), cursor


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_separator_row(row: list[str]) -> bool:
    if not row:
        return True
    return all(_TABLE_SEP.match(cell or "") or not cell for cell in row)


def _column_index(header: list[str], names: tuple[str, ...]) -> int | None:
    for index, cell in enumerate(header):
        normalized = re.sub(r"[^a-z]+", "", cell.lower())
        if normalized in names:
            return index
    return None


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(row):
        return ""
    return strip_inline_markdown(row[index])


def _consume_list(
    lines: list[str],
    index: int,
    pattern: re.Pattern[str],
) -> tuple[list[str], int]:
    items: list[str] = []
    while index < len(lines):
        stripped = lines[index].strip()
        match = pattern.match(stripped)
        if not match:
            break
        text = match.group(match.lastindex or 1)
        index += 1
        while index < len(lines) and not _starts_new_block(lines[index]):
            text = f"{text} {lines[index].strip()}"
            index += 1
        items.append(strip_inline_markdown(text))
    return items, index


def _consume_paragraph(lines: list[str], index: int) -> tuple[str, int]:
    collected: list[str] = []
    while index < len(lines) and not _starts_new_block(lines[index]):
        collected.append(lines[index].strip())
        index += 1
    return " ".join(collected).strip(), index


def _group_risks(blocks: list[Block]) -> list[Block]:
    grouped: list[Block] = []
    risks: list[RiskItem] = []
    pending: str | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending:
            risks.append(RiskItem(pending, ""))
            pending = None

    def flush_risks() -> None:
        nonlocal risks
        if risks:
            grouped.append(RiskListBlock(risks))
            risks = []

    for block in blocks:
        if isinstance(block, ParagraphBlock):
            text = block.text.strip()
            lowered = text.lower()
            if lowered.startswith("mitigation:"):
                mitigation = text.split(":", 1)[1].strip()
                if pending:
                    risks.append(RiskItem(pending, mitigation))
                    pending = None
                elif risks:
                    risks[-1].mitigation = mitigation
                else:
                    risks.append(RiskItem("", mitigation))
            else:
                flush_pending()
                pending = text
            continue
        if isinstance(block, BulletListBlock):
            flush_pending()
            for item in block.items:
                lowered = item.lower()
                if lowered.startswith("mitigation:") and risks:
                    risks[-1].mitigation = item.split(":", 1)[1].strip()
                else:
                    risks.append(RiskItem(item, ""))
            continue
        flush_pending()
        flush_risks()
        grouped.append(block)
    flush_pending()
    flush_risks()
    return grouped
