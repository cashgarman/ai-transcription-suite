"""Shared state and small widgets for the Prompt Lab tabs.

`LabContext` is the one object every tab holds: the store, the settings, the job
runner, and the signals that tell the other tabs something on disk changed. Tabs
never reach into each other.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QWidget,
)

from speaker_transcriber.config import OLLAMA_CTX_CHOICES, format_ctx_label
from speaker_transcriber.prompts import SUMMARY_STYLES
from speaker_transcriber.promptlab.settings import LabSettings, LabSettingsStore
from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.ui.promptlab.workers import LabJobRunner


class LabContext(QObject):
    """Everything the tabs share, plus the signals that keep them in step."""

    transcripts_changed = Signal()
    runs_changed = Signal()
    scores_changed = Signal()
    variants_changed = Signal()
    verdicts_changed = Signal()
    models_changed = Signal(list)
    status = Signal(str)

    def __init__(
        self,
        store: LabStore,
        settings: LabSettings,
        settings_store: LabSettingsStore,
        runner: LabJobRunner,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self.settings_store = settings_store
        self.runner = runner
        self.available_models: list[str] = []

    def save_settings(self) -> None:
        self.settings_store.save(self.settings)

    def set_models(self, names: list[str]) -> None:
        self.available_models = list(names)
        self.models_changed.emit(list(names))


class MarkdownView(QTextBrowser):
    """A read-only Markdown pane sized for reading a whole document."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)

    def show_markdown(self, markdown: str) -> None:
        self.setMarkdown(markdown or "")

    def show_plain(self, text: str) -> None:
        self.setPlainText(text or "")


def heading(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: palette(mid);")
    return label


def monospace(widget: QWidget) -> QWidget:
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(max(8, widget.font().pointSize() - 1))
    widget.setFont(font)
    return widget


def make_table(headers: Iterable[str], *, multi_select: bool = False) -> QTableWidget:
    columns = list(headers)
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(
        QAbstractItemView.SelectionMode.ExtendedSelection
        if multi_select
        else QAbstractItemView.SelectionMode.SingleSelection
    )
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(False)
    header = table.horizontalHeader()
    header.setStretchLastSection(True)
    for index in range(len(columns)):
        header.setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
    return table


def set_row(
    table: QTableWidget,
    row: int,
    values: Iterable[str],
    *,
    identifier: str = "",
    tooltip: str = "",
) -> None:
    for column, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        if column == 0 and identifier:
            item.setData(Qt.ItemDataRole.UserRole, identifier)
        if tooltip:
            item.setToolTip(tooltip)
        table.setItem(row, column, item)


def selected_ids(table: QTableWidget) -> list[str]:
    ids: list[str] = []
    for index in sorted({item.row() for item in table.selectedItems()}):
        cell = table.item(index, 0)
        if cell is None:
            continue
        identifier = cell.data(Qt.ItemDataRole.UserRole)
        if identifier:
            ids.append(str(identifier))
    return ids


def current_id(table: QTableWidget) -> str:
    row = table.currentRow()
    if row < 0:
        return ""
    cell = table.item(row, 0)
    if cell is None:
        return ""
    return str(cell.data(Qt.ItemDataRole.UserRole) or "")


def select_id(table: QTableWidget, identifier: str) -> bool:
    for row in range(table.rowCount()):
        cell = table.item(row, 0)
        if cell is not None and str(cell.data(Qt.ItemDataRole.UserRole) or "") == identifier:
            table.selectRow(row)
            return True
    return False


def ctx_combo(current: int) -> QComboBox:
    combo = QComboBox()
    for choice in OLLAMA_CTX_CHOICES:
        combo.addItem(format_ctx_label(choice), choice)
    index = combo.findData(current)
    combo.setCurrentIndex(index if index >= 0 else 1)
    return combo


def style_combo(current: str) -> QComboBox:
    combo = QComboBox()
    for style in SUMMARY_STYLES:
        combo.addItem(style.display_name, style.style_id)
    index = combo.findData(current)
    if index >= 0:
        combo.setCurrentIndex(index)
    return combo


def fill_models(combo: QComboBox, names: list[str], current: str) -> None:
    """Repopulate a model combo without losing the current choice."""
    chosen = combo.currentText() or current
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(names)
    if chosen:
        index = combo.findText(chosen)
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.isEditable():
            combo.setCurrentText(chosen)
    combo.blockSignals(False)


def model_combo(current: str) -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    combo.setMinimumWidth(220)
    if current:
        combo.addItem(current)
        combo.setCurrentText(current)
    return combo


def elide(text: str, limit: int = 80) -> str:
    body = " ".join(str(text or "").split())
    return body if len(body) <= limit else body[: limit - 1] + "…"


def score_text(value: float) -> str:
    return f"{value:.2f}" if value else "—"
