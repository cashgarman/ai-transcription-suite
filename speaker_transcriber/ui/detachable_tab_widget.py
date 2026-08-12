from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QCloseEvent

from speaker_transcriber.ui.branding import summit_icon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class DetachedPlaceholder(QWidget):
    """Stand-in kept in the tab bar while its content lives in its own window."""

    redock_requested = Signal()
    raise_requested = Signal()

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addStretch(1)

        message = QLabel(f"{title} is open in a separate window.")
        message.setObjectName("detachedPlaceholderText")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(message)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        show_button = QPushButton("Show window")
        show_button.clicked.connect(lambda: self.raise_requested.emit())
        redock_button = QPushButton("Redock")
        redock_button.setObjectName("primaryButton")
        redock_button.clicked.connect(lambda: self.redock_requested.emit())
        button_row.addStretch(1)
        button_row.addWidget(show_button)
        button_row.addWidget(redock_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        layout.addStretch(1)


class FloatingTabWindow(QWidget):
    """Top-level window hosting a tab's content while it is torn away."""

    closed = Signal()

    def __init__(self, title: str, content: QWidget) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("floatingTabWindow")
        self.setWindowTitle(f"{title} — Summit")
        self.setWindowIcon(summit_icon())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(content)
        content.show()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.closed.emit()
        event.accept()


@dataclass
class _TabEntry:
    tab_id: str
    title: str
    content: QWidget
    placeholder: DetachedPlaceholder | None = None
    window: FloatingTabWindow | None = None

    @property
    def detached(self) -> bool:
        return self.window is not None


class DetachableTabWidget(QTabWidget):
    """Tab widget whose tabs can be torn away into windows and docked back.

    Detaching reparents the original content widget, so callers keep updating
    the same instance whether it is docked or floating.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: dict[str, _TabEntry] = {}
        tab_bar = self.tabBar()
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._show_tab_menu)
        self.tabBarDoubleClicked.connect(self._on_tab_double_clicked)

    def add_detachable_tab(self, content: QWidget, title: str, *, tab_id: str) -> None:
        entry = _TabEntry(tab_id=tab_id, title=title, content=content)
        self._entries[tab_id] = entry
        self._apply_tab_tooltip(self.addTab(content, title), entry)

    def detach(self, tab_id: str) -> None:
        entry = self._entries.get(tab_id)
        if entry is None or entry.detached:
            return
        index = self.indexOf(entry.content)
        if index < 0:
            return

        size = entry.content.size()
        placeholder = DetachedPlaceholder(entry.title)
        placeholder.redock_requested.connect(lambda: self.dock(tab_id))
        placeholder.raise_requested.connect(lambda: self.raise_tab(tab_id))

        self.removeTab(index)
        window = FloatingTabWindow(entry.title, entry.content)
        window.closed.connect(lambda: self.dock(tab_id))
        entry.placeholder = placeholder
        entry.window = window

        self.insertTab(index, placeholder, entry.title)
        self._apply_tab_tooltip(index, entry)
        self.setCurrentIndex(index)
        window.resize(max(size.width(), 640), max(size.height(), 480))
        window.show()

    def dock(self, tab_id: str) -> None:
        entry = self._entries.get(tab_id)
        if entry is None or entry.window is None:
            return
        window = entry.window
        placeholder = entry.placeholder
        entry.window = None
        entry.placeholder = None
        window.closed.disconnect()

        index = self.indexOf(placeholder) if placeholder is not None else -1
        if index < 0:
            index = self.count()
        else:
            self.removeTab(index)
        self.insertTab(index, entry.content, entry.title)
        self._apply_tab_tooltip(index, entry)
        self.setCurrentWidget(entry.content)
        if placeholder is not None:
            placeholder.deleteLater()
        window.close()
        window.deleteLater()

    def dock_all(self) -> None:
        for tab_id in list(self._entries):
            self.dock(tab_id)

    def raise_tab(self, tab_id: str) -> None:
        entry = self._entries.get(tab_id)
        if entry is None or entry.window is None:
            return
        entry.window.show()
        entry.window.raise_()
        entry.window.activateWindow()

    def ensure_visible(self, content: QWidget) -> None:
        """Bring a tab's content to the front, docked or floating."""
        entry = self._entry_for_widget(content)
        if entry is None:
            self.setCurrentWidget(content)
            return
        if entry.detached:
            self.raise_tab(entry.tab_id)
        else:
            self.setCurrentWidget(entry.content)

    def _apply_tab_tooltip(self, index: int, entry: _TabEntry) -> None:
        if entry.detached:
            hint = f"Double-click to bring the {entry.title} window to the front."
        else:
            hint = f"Double-click to open {entry.title} in its own window."
        self.setTabToolTip(index, hint)

    def _entry_for_widget(self, widget: QWidget | None) -> _TabEntry | None:
        current = widget
        while current is not None:
            entry = self._entry_for_content(current)
            if entry is not None:
                return entry
            current = current.parentWidget()
        return None

    def _entry_for_content(self, content: QWidget) -> _TabEntry | None:
        for entry in self._entries.values():
            if entry.content is content:
                return entry
        return None

    def _entry_at(self, index: int) -> _TabEntry | None:
        widget = self.widget(index)
        if widget is None:
            return None
        for entry in self._entries.values():
            if widget is entry.content or widget is entry.placeholder:
                return entry
        return None

    def _show_tab_menu(self, position: QPoint) -> None:
        tab_bar = self.tabBar()
        index = tab_bar.tabAt(position)
        entry = self._entry_at(index) if index >= 0 else None
        if entry is None:
            return
        menu = QMenu(self)
        if entry.detached:
            toggle_action = menu.addAction(f"Dock {entry.title}")
            show_action = menu.addAction(f"Show {entry.title} window")
        else:
            toggle_action = menu.addAction(f"Detach {entry.title}")
            show_action = None
        chosen = menu.exec(tab_bar.mapToGlobal(position))
        if chosen is None:
            return
        if chosen is toggle_action:
            if entry.detached:
                self.dock(entry.tab_id)
            else:
                self.detach(entry.tab_id)
        elif chosen is show_action:
            self.raise_tab(entry.tab_id)

    def _on_tab_double_clicked(self, index: int) -> None:
        entry = self._entry_at(index)
        if entry is None:
            return
        if entry.detached:
            self.raise_tab(entry.tab_id)
        else:
            self.detach(entry.tab_id)
