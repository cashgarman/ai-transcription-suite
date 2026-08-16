"""Modal picker for which sections a summary should include.

The choices are registry-driven: every style declares its own toggleable
sections on its ``SummaryStyle`` entry, so a new style — or a new section on an
existing style — shows up here without any dialog changes. The dialog always
opens so the user can also choose whether to omit speaker names from narrative
notes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.prompts import get_style, style_sections


@dataclass(frozen=True)
class SummarySectionsChoices:
    excluded_section_ids: tuple[str, ...]
    omit_speaker_names: bool


class SummarySectionsDialog(QDialog):
    """Checkboxes for every optional section of the selected summary style."""

    def __init__(
        self,
        style_id: str,
        excluded_ids: Iterable[str] = (),
        *,
        omit_speaker_names: bool = False,
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

        self.omit_speaker_names_box = QCheckBox(
            "Keep names only for participants and assigned callouts"
        )
        self.omit_speaker_names_box.setChecked(omit_speaker_names)
        layout.addWidget(self.omit_speaker_names_box)
        omit_description = QLabel(
            "When enabled, discussion notes avoid inline speaker attribution "
            "(no \"Ada said\" or \"- Ada: …\" bullets). Names still appear in "
            "the participants list and in action items, owners, shoutouts, and "
            "other person-specific callouts."
        )
        omit_description.setWordWrap(True)
        omit_description.setIndent(24)
        omit_description.setStyleSheet("color: palette(mid);")
        layout.addWidget(omit_description)

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
        self.omit_speaker_names_box.setChecked(False)

    def excluded_section_ids(self) -> tuple[str, ...]:
        """The ids the user unchecked, in registry order."""
        return tuple(
            section_id
            for section_id, box in self._boxes.items()
            if not box.isChecked()
        )

    def choices(self) -> SummarySectionsChoices:
        return SummarySectionsChoices(
            excluded_section_ids=self.excluded_section_ids(),
            omit_speaker_names=self.omit_speaker_names_box.isChecked(),
        )

    @classmethod
    def ask(
        cls,
        style_id: str,
        excluded_ids: Iterable[str] = (),
        *,
        omit_speaker_names: bool = False,
        parent: QWidget | None = None,
    ) -> SummarySectionsChoices | None:
        """The user's section and attribution choices, or None when cancelled."""
        dialog = cls(
            style_id,
            excluded_ids,
            omit_speaker_names=omit_speaker_names,
            parent=parent,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.choices()
