from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QListView, QStyledItemDelegate, QStyle

from speaker_transcriber.models.summarization import OllamaModelInfo


class OllamaModelItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        if not index.isValid():
            return
        model = index.model()
        if model is None:
            return
        name = str(model.index(index.row(), 0).data(Qt.ItemDataRole.DisplayRole) or "")
        vram = str(model.index(index.row(), 1).data(Qt.ItemDataRole.DisplayRole) or "")
        painter.save()
        style = option.widget.style() if option.widget else None
        if style is not None:
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem,
                option,
                painter,
                option.widget,
            )
        rect = option.rect.adjusted(8, 0, -8, 0)
        name_width = int(rect.width() * 0.68)
        name_rect = rect.adjusted(0, 0, -(rect.width() - name_width), 0)
        vram_rect = rect.adjusted(name_width, 0, 0, 0)
        painter.drawText(
            name_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            name,
        )
        painter.drawText(
            vram_rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            vram,
        )
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), 24))
        return size


class OllamaModelComboBox(QComboBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._item_model = QStandardItemModel(0, 2, self)
        self.setModel(self._item_model)
        self.setModelColumn(0)
        view = QListView(self)
        view.setItemDelegate(OllamaModelItemDelegate(view))
        view.setMinimumWidth(460)
        self.setView(view)
        self.setMinimumWidth(320)

    def set_models(self, models: list[OllamaModelInfo]) -> None:
        self._item_model.removeRows(0, self._item_model.rowCount())
        for model in models:
            name_item = QStandardItem(model.name)
            name_item.setData(model.name, Qt.ItemDataRole.UserRole)
            vram_item = QStandardItem(model.approx_vram_label)
            vram_item.setFlags(vram_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._item_model.appendRow([name_item, vram_item])

    def set_placeholder(self, text: str, enabled: bool = True) -> None:
        self._item_model.removeRows(0, self._item_model.rowCount())
        name_item = QStandardItem(text)
        name_item.setData(None, Qt.ItemDataRole.UserRole)
        self._item_model.appendRow([name_item, QStandardItem("")])
        self.setEnabled(enabled)

    def current_model_name(self) -> str | None:
        index = self.currentIndex()
        if index < 0:
            return None
        item = self._item_model.item(index, 0)
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def has_selectable_model(self) -> bool:
        return self.current_model_name() is not None

    def select_preferred_model(self, preferred_names: list[str]) -> None:
        for preferred in preferred_names:
            for row in range(self._item_model.rowCount()):
                item = self._item_model.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == preferred:
                    self.setCurrentIndex(row)
                    return
        if self._item_model.rowCount() > 0:
            self.setCurrentIndex(0)
