"""Modal picker for which sections a summary should include.

The choices are registry-driven: every style declares its own toggleable
sections on its ``SummaryStyle`` entry, so a new style — or a new section on an
existing style — shows up here without any dialog changes. Styles that declare
no sections (the sequential transcripts) never show the dialog at all.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.prompts import get_style, style_sections


class SummarySectionsDialog(QDialog):
    """Checkboxes for every optional section of the selected summary style."""

    def __init__(
        self,
        style_id: str,
        excluded_ids: Iterable[str] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        style = get_style(style_id)
        excluded = {str(item) for item in excluded_ids or ()}
        self._style = style
        self._boxes: dict[str, QCheckBox] = {}

        self.setWindowTitle(f"Summarize — {style.display_name}")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        intro = QLabel(
            f"Choose the sections to include in the {style.display_name} notes."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        for section in style.sections:
            box = QCheckBox(section.label)
            box.setChecked(section.section_id not in excluded)
            layout.addWidget(box)
            description = QLabel(section.description)
            description.setWordWrap(True)
            description.setIndent(24)
            description.setStyleSheet("color: palette(mid);")
            layout.addWidget(description)
            self._boxes[section.section_id] = box

        layout.addStretch()

        buttons = QDialogButtonBox()
        summarize = buttons.addButton(
            "Summarize", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        defaults = buttons.addButton(
            "Restore defaults", QDialogButtonBox.ButtonRole.ResetRole
        )
        defaults.clicked.connect(self._restore_defaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        summarize.setDefault(True)
        layout.addWidget(buttons)

    def _restore_defaults(self) -> None:
        for section in self._style.sections:
            self._boxes[section.section_id].setChecked(section.default_included)

    def excluded_section_ids(self) -> tuple[str, ...]:
        """The ids the user unchecked, in registry order."""
        return tuple(
            section_id
            for section_id, box in self._boxes.items()
            if not box.isChecked()
        )

    @classmethod
    def ask(
        cls,
        style_id: str,
        excluded_ids: Iterable[str] = (),
        parent: QWidget | None = None,
    ) -> tuple[str, ...] | None:
        """The excluded section ids, or None when the user cancelled.

        Styles with no optional sections skip the dialog and return ().
        """
        if not style_sections(style_id):
            return ()
        dialog = cls(style_id, excluded_ids, parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.excluded_section_ids()
