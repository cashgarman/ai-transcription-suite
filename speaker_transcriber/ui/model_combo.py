from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QListView, QSizePolicy, QStyledItemDelegate, QStyle

from speaker_transcriber.models.model_catalog import ADD_MODELS_SENTINEL
from speaker_transcriber.models.summarization import OllamaModelInfo, format_approx_vram
from speaker_transcriber.ui.theme import Theme


@dataclass(frozen=True)
class ComboModelItem:
    value: str
    label: str
    detail: str = ""
    selectable: bool = True
    kind: str = "model"
    installed: bool = True


class ModelItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        if not index.isValid():
            return
        model = index.model()
        if model is None:
            return
        kind = model.index(index.row(), 0).data(Qt.ItemDataRole.UserRole + 1)
        if kind == "separator":
            self._paint_separator(painter, option)
            return
        name = str(model.index(index.row(), 0).data(Qt.ItemDataRole.DisplayRole) or "")
        detail = str(model.index(index.row(), 1).data(Qt.ItemDataRole.DisplayRole) or "")
        installed = model.index(index.row(), 0).data(Qt.ItemDataRole.UserRole + 2)
        painter.save()
        style = option.widget.style() if option.widget else None
        if style is not None:
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem,
                option,
                painter,
                option.widget,
            )
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if installed is False and not selected:
            painter.setPen(QColor(Theme.TEXT_MUTED))
        elif selected:
            painter.setPen(QColor(Theme.HIGHLIGHT_TEXT))
        else:
            painter.setPen(QColor(Theme.TEXT))
        rect = option.rect.adjusted(8, 0, -8, 0)
        name_width = int(rect.width() * 0.62)
        name_rect = rect.adjusted(0, 0, -(rect.width() - name_width), 0)
        detail_rect = rect.adjusted(name_width, 0, 0, 0)
        painter.drawText(
            name_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            name,
        )
        painter.drawText(
            detail_rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            detail,
        )
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        model = index.model()
        if model is not None:
            kind = model.index(index.row(), 0).data(Qt.ItemDataRole.UserRole + 1)
            if kind == "separator":
                size.setHeight(10)
                return size
        size.setHeight(max(size.height(), 24))
        return size

    def _paint_separator(self, painter, option) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        y = option.rect.center().y() + 0.5
        left = option.rect.left() + 12
        right = option.rect.right() - 12
        fade = QColor(Theme.ACCENT)
        fade.setAlpha(0)
        mid = QColor(Theme.ACCENT)
        mid.setAlpha(90)
        accent = QLinearGradient(QPointF(left, y), QPointF(right, y))
        accent.setColorAt(0.0, fade)
        accent.setColorAt(0.5, mid)
        accent.setColorAt(1.0, fade)
        painter.setPen(QPen(accent, 1.5))
        painter.drawLine(QPointF(left, y), QPointF(right, y))
        painter.restore()


class ModelComboBox(QComboBox):
    add_models_requested = Signal()

    def __init__(self, parent=None, *, include_add: bool = True) -> None:
        super().__init__(parent)
        self._include_add = include_add
        self._restoring = False
        self._last_index = 0
        self._item_model = QStandardItemModel(0, 2, self)
        self.setModel(self._item_model)
        self.setModelColumn(0)
        view = QListView(self)
        view.setItemDelegate(ModelItemDelegate(view))
        view.setMinimumWidth(420)
        self.setView(view)
        self.setMinimumWidth(120)
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.setMinimumContentsLength(8)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.currentIndexChanged.connect(self._on_index_changed)

    def set_items(self, items: list[ComboModelItem], *, include_add: bool | None = None) -> None:
        add_row = self._include_add if include_add is None else include_add
        previous = self.current_value()
        self._item_model.removeRows(0, self._item_model.rowCount())
        for item in items:
            self._append_item(item)
        if add_row:
            if self._item_model.rowCount() > 0:
                self._append_separator()
            self._append_item(
                ComboModelItem(
                    value=ADD_MODELS_SENTINEL,
                    label="Add Models…",
                    kind="add",
                )
            )
        if previous:
            self.select_preferred([previous])
        elif self._item_model.rowCount() > 0:
            self.setCurrentIndex(0)
        self._last_index = max(0, self.currentIndex())
        self._sync_closed_appearance()

    def set_models(self, models: list[OllamaModelInfo]) -> None:
        items = [
            ComboModelItem(
                value=model.name,
                label=model.name,
                detail=model.approx_vram_label,
            )
            for model in models
        ]
        self.set_items(items)

    def set_placeholder(self, text: str, enabled: bool = True) -> None:
        self._item_model.removeRows(0, self._item_model.rowCount())
        name_item = QStandardItem(text)
        name_item.setData(None, Qt.ItemDataRole.UserRole)
        name_item.setData("placeholder", Qt.ItemDataRole.UserRole + 1)
        self._item_model.appendRow([name_item, QStandardItem("")])
        if self._include_add:
            self._append_separator()
            self._append_item(
                ComboModelItem(
                    value=ADD_MODELS_SENTINEL,
                    label="Add Models…",
                    kind="add",
                )
            )
        self.setEnabled(enabled)
        self._last_index = 0

    def current_value(self) -> str | None:
        index = self.currentIndex()
        if index < 0:
            return None
        item = self._item_model.item(index, 0)
        if item is None:
            return None
        kind = item.data(Qt.ItemDataRole.UserRole + 1)
        if kind in {"add", "placeholder", "separator"}:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def current_model_name(self) -> str | None:
        return self.current_value()

    def has_selectable_model(self) -> bool:
        return self.current_value() is not None

    def select_preferred(self, preferred_names: list[str]) -> None:
        for preferred in preferred_names:
            if not preferred:
                continue
            for row in range(self._item_model.rowCount()):
                item = self._item_model.item(row, 0)
                if item and (
                    item.data(Qt.ItemDataRole.UserRole) == preferred
                    or str(item.data(Qt.ItemDataRole.UserRole) or "").startswith(
                        f"{preferred}:"
                    )
                ):
                    self._restoring = True
                    self.setCurrentIndex(row)
                    self._restoring = False
                    self._last_index = row
                    self._sync_closed_appearance()
                    return
        for row in range(self._item_model.rowCount()):
            item = self._item_model.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole + 1) == "model":
                self._restoring = True
                self.setCurrentIndex(row)
                self._restoring = False
                self._last_index = row
                self._sync_closed_appearance()
                return
        self._sync_closed_appearance()

    def select_preferred_model(self, preferred_names: list[str]) -> None:
        self.select_preferred(preferred_names)

    def _append_separator(self) -> None:
        separator = QStandardItem("")
        separator.setFlags(Qt.ItemFlag.NoItemFlags)
        separator.setData("separator", Qt.ItemDataRole.UserRole + 1)
        detail = QStandardItem("")
        detail.setFlags(Qt.ItemFlag.NoItemFlags)
        self._item_model.appendRow([separator, detail])

    def _append_item(self, item: ComboModelItem) -> None:
        name_item = QStandardItem(item.label)
        name_item.setData(item.value, Qt.ItemDataRole.UserRole)
        name_item.setData(item.kind, Qt.ItemDataRole.UserRole + 1)
        name_item.setData(item.installed, Qt.ItemDataRole.UserRole + 2)
        if not item.selectable:
            name_item.setEnabled(False)
        color = QColor(Theme.TEXT_MUTED) if (
            item.kind == "model" and not item.installed
        ) else QColor(Theme.TEXT)
        name_item.setForeground(color)
        detail_item = QStandardItem(item.detail)
        detail_item.setFlags(detail_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        detail_item.setForeground(color)
        self._item_model.appendRow([name_item, detail_item])

    def _on_index_changed(self, index: int) -> None:
        if self._restoring:
            return
        item = self._item_model.item(index, 0)
        kind = item.data(Qt.ItemDataRole.UserRole + 1) if item is not None else None
        if kind == "add":
            self._restoring = True
            self.blockSignals(True)
            self.setCurrentIndex(self._last_index)
            self.blockSignals(False)
            self._restoring = False
            self.add_models_requested.emit()
            self._sync_closed_appearance()
            return
        if kind in {"placeholder", "separator"}:
            if kind == "separator":
                self._restoring = True
                self.setCurrentIndex(self._last_index)
                self._restoring = False
            self._sync_closed_appearance()
            return
        self._last_index = index
        self._sync_closed_appearance()

    def _sync_closed_appearance(self) -> None:
        item = self._item_model.item(max(0, self.currentIndex()), 0)
        installed = True
        if item is not None and item.data(Qt.ItemDataRole.UserRole + 1) == "model":
            installed = item.data(Qt.ItemDataRole.UserRole + 2) is not False
        self.setProperty("modelInstalled", "true" if installed else "false")
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()
        view = self.view()
        if view is not None and view.viewport() is not None:
            view.viewport().update()


class OllamaModelComboBox(ModelComboBox):
    """Backward-compatible alias used by existing Ollama wiring."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, include_add=True)


def combo_item_from_catalog(entry, *, vram: bool = True) -> ComboModelItem:
    detail = entry.role or entry.status_label
    if vram and entry.size_bytes:
        detail = format_approx_vram(entry.size_bytes)
        if entry.role:
            detail = f"{entry.role} · {detail}"
    return ComboModelItem(
        value=entry.name,
        label=entry.label,
        detail=detail,
        selectable=True,
        kind="model",
        installed=bool(entry.installed),
    )
