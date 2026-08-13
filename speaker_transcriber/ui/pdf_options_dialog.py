"""Modal picker for how the notes PDF should be generated.

The choices are registry-driven: ``PDF_OPTIONS`` declares every toggle once,
so a new option appears here — and persists, and reaches both PDF engines —
without any dialog changes. Options that make no difference for the current
style's layout (a cover page for a newsletter, say) are not shown, and when
nothing applies the dialog is skipped entirely.
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.export.pdf_options import (
    PdfOption,
    applicable_pdf_options,
    effective_pdf_options,
)
from speaker_transcriber.prompts import style_display_name


class PdfOptionsDialog(QDialog):
    """Checkboxes for every PDF option that applies to the selected style."""

    def __init__(
        self,
        style_id: str,
        values: Mapping[str, bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._values = effective_pdf_options(values)
        self._options: tuple[PdfOption, ...] = applicable_pdf_options(style_id)
        self._boxes: dict[str, QCheckBox] = {}
        display_name = style_display_name(style_id)

        self.setWindowTitle(f"Export PDF — {display_name}")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        intro = QLabel(f"Choose how to generate the {display_name} PDF.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

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

    def _restore_defaults(self) -> None:
        for option in self._options:
            self._boxes[option.option_id].setChecked(option.default)

    def selected_options(self) -> dict[str, bool]:
        """Every option's value: the shown boxes, plus untouched stored ones."""
        values = dict(self._values)
        for option_id, box in self._boxes.items():
            values[option_id] = box.isChecked()
        return values

    @classmethod
    def ask(
        cls,
        style_id: str,
        values: Mapping[str, bool] | None = None,
        parent: QWidget | None = None,
    ) -> dict[str, bool] | None:
        """The chosen options, or None when the user cancelled.

        Styles with no applicable options skip the dialog and export with the
        stored values.
        """
        if not applicable_pdf_options(style_id):
            return effective_pdf_options(values)
        dialog = cls(style_id, values, parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.selected_options()
