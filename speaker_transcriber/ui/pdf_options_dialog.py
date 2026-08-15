"""Modal picker for how the notes PDF should be generated.

Both halves are registry-driven: ``PDF_THEME_CHOICES`` supplies the colour
schemes and ``PDF_OPTIONS`` the toggles, so a new theme or option appears
here — and persists, and reaches both PDF engines — with no dialog changes.
Options that make no difference for the current style's layout (a cover page
for a newsletter, say) are hidden; the theme always applies.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.export.pdf_options import (
    PdfExportChoices,
    PdfOption,
    applicable_pdf_options,
    effective_pdf_options,
)
from speaker_transcriber.export.pdf_theme import (
    PDF_THEME_CHOICES,
    PdfPalette,
    normalize_theme,
    palette_for,
    theme_for,
)
from speaker_transcriber.prompts import style_display_name


class ThemePreview(QWidget):
    """A miniature of the first page in the selected theme's colours."""

    def __init__(self, palette: PdfPalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self.setFixedHeight(104)
        self.setMinimumWidth(240)

    def show_palette(self, palette: PdfPalette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self._palette
        page = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        painter.setPen(QPen(QColor(palette.border), 1))
        painter.setBrush(QColor(palette.page))
        painter.drawRoundedRect(page, 5, 5)

        left = page.left() + 14
        width = page.width() - 28
        painter.setPen(Qt.PenStyle.NoPen)

        def bar(top: float, fraction: float, height: float, color: str) -> None:
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(
                QRectF(left, page.top() + top, width * fraction, height), 1.5, 1.5
            )

        bar(13, 0.22, 4, palette.accent)
        bar(23, 0.62, 11, palette.heading)
        bar(41, 1.0, 2, palette.rule_strong)
        bar(50, 0.92, 4, palette.text)
        bar(59, 0.74, 4, palette.muted)

        header = QRectF(left, page.top() + 71, width * 0.55, 16)
        painter.setBrush(QColor(palette.table_header_background))
        painter.drawRoundedRect(header, 2, 2)
        painter.setBrush(QColor(palette.table_header_text))
        painter.drawRoundedRect(
            QRectF(header.left() + 6, header.top() + 6, header.width() * 0.5, 4),
            1.5,
            1.5,
        )

        dot = page.right() - 16
        for color in reversed(palette.participants[:4]):
            painter.setBrush(QColor(color))
            painter.drawEllipse(QRectF(dot, page.top() + 74, 9, 9))
            dot -= 13


class PdfOptionsDialog(QDialog):
    """The colour theme plus every PDF option that applies to the style."""

    def __init__(
        self,
        style_id: str,
        theme: str | None = None,
        options: Mapping[str, bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._style_id = style_id
        self._values = effective_pdf_options(options)
        self._options: tuple[PdfOption, ...] = applicable_pdf_options(style_id)
        self._boxes: dict[str, QCheckBox] = {}
        display_name = style_display_name(style_id)

        self.setWindowTitle(f"Export PDF — {display_name}")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        intro = QLabel(f"Choose how to generate the {display_name} PDF.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.theme_combo = QComboBox()
        theme_view = QListView()
        theme_view.setMinimumWidth(220)
        self.theme_combo.setView(theme_view)
        for entry in PDF_THEME_CHOICES:
            self.theme_combo.addItem(entry.label, entry.theme_id)
            self.theme_combo.setItemData(
                self.theme_combo.count() - 1,
                entry.description,
                Qt.ItemDataRole.ToolTipRole,
            )
        self.theme_combo.setCurrentIndex(
            max(self.theme_combo.findData(normalize_theme(theme)), 0)
        )

        theme_row = QHBoxLayout()
        theme_row.setSpacing(8)
        theme_row.addWidget(QLabel("Colour theme"))
        theme_row.addWidget(self.theme_combo, 1)
        layout.addLayout(theme_row)

        self.preview = ThemePreview(self._preview_palette())
        layout.addWidget(self.preview)

        self._theme_description = QLabel()
        self._theme_description.setWordWrap(True)
        self._theme_description.setStyleSheet("color: palette(mid);")
        layout.addWidget(self._theme_description)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self._on_theme_changed()

        if self._options:
            divider = QFrame()
            divider.setFrameShape(QFrame.Shape.HLine)
            divider.setFrameShadow(QFrame.Shadow.Sunken)
            layout.addWidget(divider)

        for option in self._options:
            box = QCheckBox(option.label)
            box.setChecked(self._values[option.option_id])
            layout.addWidget(box)
            description = QLabel(option.description)
            description.setWordWrap(True)
            description.setIndent(24)
            description.setStyleSheet("color: palette(mid);")
            layout.addWidget(description)
            self._boxes[option.option_id] = box

        layout.addStretch()

        buttons = QDialogButtonBox()
        export = buttons.addButton("Export…", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        defaults = buttons.addButton(
            "Restore defaults", QDialogButtonBox.ButtonRole.ResetRole
        )
        defaults.clicked.connect(self._restore_defaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        export.setDefault(True)
        layout.addWidget(buttons)

    def _preview_palette(self) -> PdfPalette:
        return palette_for(self.selected_theme(), self._style_id)

    def _on_theme_changed(self, _index: int = 0) -> None:
        self.preview.show_palette(self._preview_palette())
        self._theme_description.setText(theme_for(self.selected_theme()).description)

    def _restore_defaults(self) -> None:
        self.theme_combo.setCurrentIndex(
            max(self.theme_combo.findData(PDF_THEME_CHOICES[0].theme_id), 0)
        )
        for option in self._options:
            self._boxes[option.option_id].setChecked(option.default)

    def selected_theme(self) -> str:
        return normalize_theme(self.theme_combo.currentData())

    def selected_options(self) -> dict[str, bool]:
        """Every option's value: the shown boxes, plus untouched stored ones."""
        values = dict(self._values)
        for option_id, box in self._boxes.items():
            values[option_id] = box.isChecked()
        return values

    def choices(self) -> PdfExportChoices:
        return PdfExportChoices(self.selected_theme(), self.selected_options())

    @classmethod
    def ask(
        cls,
        style_id: str,
        theme: str | None = None,
        options: Mapping[str, bool] | None = None,
        parent: QWidget | None = None,
    ) -> PdfExportChoices | None:
        """The chosen theme and options, or None when the user cancelled."""
        dialog = cls(style_id, theme, options, parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.choices()
