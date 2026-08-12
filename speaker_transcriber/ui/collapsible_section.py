from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class CollapsibleSection(QFrame):
    """Themed panel with a chevron toggle instead of a checkbox."""

    def __init__(
        self,
        title: str,
        parent=None,
        *,
        expanded: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("collapsibleSection")
        self.setFrameShape(QFrame.Shape.NoFrame)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("collapsibleHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(8)

        self._toggle = QToolButton()
        self._toggle.setObjectName("collapseToggle")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setAutoRaise(True)
        self._toggle.setText(title)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.toggled.connect(self._on_toggled)
        header_layout.addWidget(self._toggle, 1)
        root.addWidget(header)

        self._content = QWidget()
        self._content.setObjectName("collapsibleContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 4, 12, 12)
        self._content_layout.setSpacing(8)
        root.addWidget(self._content)

        self._sync_arrow()
        self._content.setVisible(expanded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def add_widget(self, widget: QWidget) -> None:
        self._content_layout.addWidget(widget)

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        self._toggle.setChecked(expanded)

    def _on_toggled(self, expanded: bool) -> None:
        self._content.setVisible(expanded)
        self._sync_arrow()

    def _sync_arrow(self) -> None:
        if self._toggle.isChecked():
            self._toggle.setArrowType(Qt.ArrowType.DownArrow)
            self._toggle.setToolTip("Collapse")
        else:
            self._toggle.setArrowType(Qt.ArrowType.RightArrow)
            self._toggle.setToolTip("Expand")
