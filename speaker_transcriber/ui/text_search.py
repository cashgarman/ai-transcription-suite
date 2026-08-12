from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QKeyEvent,
    QKeySequence,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.ui.theme import Theme


_MATCH_BACKGROUND = QColor("#C9A44A")
_CURRENT_BACKGROUND = QColor(Theme.ACCENT)
_MATCH_FOREGROUND = QColor(Theme.HIGHLIGHT_TEXT)


class TextFinder:
    """Case-insensitive find-in-document helper for a QTextDocument."""

    def __init__(self) -> None:
        self.query = ""
        self.matches: list[QTextCursor] = []
        self.index = -1

    def status(self) -> tuple[int, int]:
        if not self.matches:
            return (0, 0)
        return (self.index + 1, len(self.matches))

    def set_query(
        self,
        document: QTextDocument,
        query: str,
        *,
        from_position: int = 0,
    ) -> None:
        self.query = query
        self._find(document, from_position)

    def refresh(self, document: QTextDocument, *, from_position: int | None = None) -> None:
        position = from_position
        if position is None and 0 <= self.index < len(self.matches):
            position = self.matches[self.index].selectionStart()
        if position is None:
            position = 0
        self._find(document, position)

    def goto(self, delta: int) -> QTextCursor | None:
        if not self.matches:
            return None
        self.index = (self.index + delta) % len(self.matches)
        return self.matches[self.index]

    def current_cursor(self) -> QTextCursor | None:
        if 0 <= self.index < len(self.matches):
            return self.matches[self.index]
        return None

    def extra_selections(self) -> list[QTextEdit.ExtraSelection]:
        selections: list[QTextEdit.ExtraSelection] = []
        match_format = QTextCharFormat()
        match_format.setBackground(_MATCH_BACKGROUND)
        match_format.setForeground(_MATCH_FOREGROUND)
        current_format = QTextCharFormat()
        current_format.setBackground(_CURRENT_BACKGROUND)
        current_format.setForeground(_MATCH_FOREGROUND)
        for index, cursor in enumerate(self.matches):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(cursor)
            selection.format = current_format if index == self.index else match_format
            selections.append(selection)
        return selections

    def _find(self, document: QTextDocument, from_position: int) -> None:
        self.matches = []
        self.index = -1
        query = self.query
        if not query:
            return
        cursor = QTextCursor(document)
        while True:
            cursor = document.find(query, cursor)
            if cursor.isNull():
                break
            self.matches.append(QTextCursor(cursor))
        if not self.matches:
            return
        for index, match in enumerate(self.matches):
            if match.selectionStart() >= from_position:
                self.index = index
                return
        self.index = 0


class TextSearchBar(QWidget):
    query_changed = Signal(str)
    next_requested = Signal()
    previous_requested = Signal()

    def __init__(self, placeholder: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("textSearchBar")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.setClearButtonEnabled(True)
        self._input.setToolTip("Find in this tab (Ctrl+F)")
        self._input.textChanged.connect(self.query_changed.emit)
        self._input.installEventFilter(self)

        self._status = QLabel("")
        self._status.setObjectName("searchMatchStatus")
        self._status.setMinimumWidth(80)
        self._status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self._prev = QToolButton()
        self._prev.setText("Prev")
        self._prev.setToolTip("Previous match (Shift+Enter)")
        self._prev.setEnabled(False)
        self._prev.clicked.connect(self.previous_requested.emit)

        self._next = QToolButton()
        self._next.setText("Next")
        self._next.setToolTip("Next match (Enter)")
        self._next.setEnabled(False)
        self._next.clicked.connect(self.next_requested.emit)

        layout.addWidget(self._input, 1)
        layout.addWidget(self._status)
        layout.addWidget(self._prev)
        layout.addWidget(self._next)

    def query(self) -> str:
        return self._input.text()

    def clear_query(self) -> None:
        self._input.clear()

    def focus_input(self) -> None:
        self._input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._input.selectAll()

    def set_match_status(self, current: int, total: int) -> None:
        has_query = bool(self._input.text())
        self._prev.setEnabled(total > 0)
        self._next.setEnabled(total > 0)
        if not has_query:
            self._status.setText("")
            self._status.setProperty("kind", "")
        elif total == 0:
            self._status.setText("No matches")
            self._status.setProperty("kind", "empty")
        else:
            self._status.setText(f"{current} of {total}")
            self._status.setProperty("kind", "")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def eventFilter(self, watched, event) -> bool:
        if watched is self._input and event.type() == QEvent.Type.KeyPress:
            key_event = event
            if not isinstance(key_event, QKeyEvent):
                return super().eventFilter(watched, event)
            if key_event.key() == Qt.Key.Key_Escape:
                if self._input.text():
                    self._input.clear()
                else:
                    self._input.clearFocus()
                return True
            if key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if key_event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.previous_requested.emit()
                else:
                    self.next_requested.emit()
                return True
        return super().eventFilter(watched, event)


class SearchableTextPanel(QWidget):
    """Wraps a QTextEdit with a find bar."""

    def __init__(
        self,
        text_edit: QTextEdit,
        *,
        placeholder: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.text_edit = text_edit
        self.search_bar = TextSearchBar(placeholder)
        self._finder = TextFinder()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self.search_bar)
        text_edit.setParent(self)
        layout.addWidget(text_edit, 1)

        self.search_bar.query_changed.connect(self._on_query_changed)
        self.search_bar.next_requested.connect(lambda: self._goto_match(1))
        self.search_bar.previous_requested.connect(lambda: self._goto_match(-1))
        self.text_edit.textChanged.connect(self._on_text_changed)
        self._bind_shortcuts()

    def focus_search(self) -> None:
        self.search_bar.focus_input()

    def clear_search(self) -> None:
        self.search_bar.clear_query()

    def _bind_shortcuts(self) -> None:
        find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        find_shortcut.activated.connect(self.focus_search)
        next_shortcut = QShortcut(QKeySequence.StandardKey.FindNext, self)
        next_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        next_shortcut.activated.connect(lambda: self._goto_match(1))
        previous_shortcut = QShortcut(QKeySequence.StandardKey.FindPrevious, self)
        previous_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        previous_shortcut.activated.connect(lambda: self._goto_match(-1))

    def _on_query_changed(self, query: str) -> None:
        self._finder.set_query(
            self.text_edit.document(),
            query,
            from_position=self.text_edit.textCursor().position(),
        )
        self._apply(reveal=True)

    def _on_text_changed(self) -> None:
        if not self._finder.query:
            return
        self._finder.refresh(self.text_edit.document())
        self._apply(reveal=False)

    def _goto_match(self, delta: int) -> None:
        if not self._finder.matches:
            return
        self._finder.goto(delta)
        self._apply(reveal=True)

    def _apply(self, *, reveal: bool) -> None:
        self.text_edit.setExtraSelections(self._finder.extra_selections())
        self.search_bar.set_match_status(*self._finder.status())
        if reveal:
            self._reveal_current()

    def _reveal_current(self) -> None:
        match = self._finder.current_cursor()
        if match is None:
            return
        cursor = QTextCursor(self.text_edit.document())
        cursor.setPosition(match.selectionStart())
        self.text_edit.setTextCursor(cursor)
        self.text_edit.ensureCursorVisible()
