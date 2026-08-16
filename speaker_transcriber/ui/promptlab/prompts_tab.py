"""Browse, edit, and version the prompts on both sides of the experiment.

Two things are editable here: the summarizer prompt variants under test, and
the lab's own generator, judge, and optimizer prompts. The second set matters
more than it looks — a judge that grades the wrong thing will happily rank a
worse prompt first.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.promptlab.lab_prompts import (
    LAB_PROMPT_FILENAMES,
    get_lab_prompt,
    reload_lab_prompts,
    save_lab_prompt,
)
from speaker_transcriber.promptlab.promptset import (
    clone_variant,
    list_variants,
    load_variant,
    stage_text,
    update_variant_stage,
    variant_diff,
)
from speaker_transcriber.promptlab.types import PROMPT_STAGES, PromptVariant
from speaker_transcriber.ui.promptlab.common import (
    LabContext,
    heading,
    hint,
    monospace,
    style_combo,
)


LAB_PROMPT_LABELS = {
    "scenario_dialogue": "Generator — grounded dialogue",
    "freeform_transcript": "Generator — free-form dialogue",
    "judge_grounded": "Judge — against ground truth",
    "judge_reference_free": "Judge — against the transcript",
    "optimizer": "Optimizer — prompt rewriter",
}


class PromptsTab(QWidget):
    def __init__(self, context: LabContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._variant: PromptVariant | None = None
        self._build()
        self.context.variants_changed.connect(self.refresh)
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        tabs = QTabWidget()
        tabs.addTab(self._variants_page(), "Summarizer prompts")
        tabs.addTab(self._lab_page(), "Lab prompts")
        layout.addWidget(tabs)

    # Summarizer prompt variants

    def _variants_page(self) -> QWidget:
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(0, 0, 0, 0)

        left = QWidget()
        left.setMaximumWidth(320)
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 8, 0)

        self.style_selector = style_combo(self.context.settings.style_id)
        self.style_selector.currentIndexChanged.connect(self.refresh)
        column.addWidget(self.style_selector)

        self.variant_list = QListWidget()
        self.variant_list.currentItemChanged.connect(self._load_variant)
        column.addWidget(self.variant_list, 1)

        self.lineage = QLabel("")
        self.lineage.setWordWrap(True)
        self.lineage.setStyleSheet("color: palette(mid);")
        column.addWidget(self.lineage)

        self.clone_button = QPushButton("Clone as new variant")
        self.clone_button.clicked.connect(self._clone)
        column.addWidget(self.clone_button)
        self.save_button = QPushButton("Save this stage")
        self.save_button.clicked.connect(self._save_stage)
        column.addWidget(self.save_button)
        self.revert_button = QPushButton("Revert stage to shipped")
        self.revert_button.clicked.connect(self._revert_stage)
        column.addWidget(self.revert_button)
        self.diff_button = QPushButton("Show diff against shipped")
        self.diff_button.clicked.connect(self._show_diff)
        column.addWidget(self.diff_button)
        self.delete_button = QPushButton("Delete variant")
        self.delete_button.clicked.connect(self._delete)
        column.addWidget(self.delete_button)

        column.addWidget(
            hint(
                "The shipped variant is read-only here. Clone it to start a "
                "candidate, edit one stage, then run both against the same "
                "transcripts."
            )
        )
        row.addWidget(left, 0)

        self.stage_tabs = QTabWidget()
        self.editors: dict[str, QPlainTextEdit] = {}
        for stage in PROMPT_STAGES:
            editor = QPlainTextEdit()
            monospace(editor)
            self.editors[stage] = editor
            self.stage_tabs.addTab(editor, stage)
        row.addWidget(self.stage_tabs, 1)
        return page

    def refresh(self) -> None:
        style_id = str(self.style_selector.currentData())
        chosen = self._variant.variant_id if self._variant else ""
        self.variant_list.blockSignals(True)
        self.variant_list.clear()
        for variant in list_variants(self.context.store, style_id):
            stages = ", ".join(variant.overridden_stages) or "as shipped"
            item = QListWidgetItem(f"{variant.label}\n{stages}")
            item.setData(Qt.ItemDataRole.UserRole, variant.variant_id)
            self.variant_list.addItem(item)
        self.variant_list.blockSignals(False)
        for row in range(self.variant_list.count()):
            item = self.variant_list.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole)) == chosen:
                self.variant_list.setCurrentRow(row)
                return
        if self.variant_list.count():
            self.variant_list.setCurrentRow(0)

    def _load_variant(self) -> None:
        item = self.variant_list.currentItem()
        if item is None:
            return
        style_id = str(self.style_selector.currentData())
        try:
            variant = load_variant(
                self.context.store, style_id, str(item.data(Qt.ItemDataRole.UserRole))
            )
        except KeyError:
            return
        self._variant = variant
        for stage, editor in self.editors.items():
            editor.setPlainText(stage_text(variant, stage))
            editor.setReadOnly(variant.is_shipped)
        overridden = set(variant.overridden_stages)
        for index, stage in enumerate(PROMPT_STAGES):
            self.stage_tabs.setTabText(index, f"{stage} *" if stage in overridden else stage)
        self.lineage.setText(
            f"id: {variant.variant_id}\nauthor: {variant.author}\n"
            f"from: {variant.parent_id or 'nothing'}\n{variant.rationale}".strip()
        )
        editable = not variant.is_shipped
        self.save_button.setEnabled(editable)
        self.revert_button.setEnabled(editable)
        self.delete_button.setEnabled(editable)

    def _current_stage(self) -> str:
        return PROMPT_STAGES[self.stage_tabs.currentIndex()]

    def _clone(self) -> None:
        if self._variant is None:
            return
        label, accepted = QInputDialog.getText(
            self, "Clone variant", "Name for the new variant:", text=f"{self._variant.label} v2"
        )
        if not accepted or not label.strip():
            return
        variant = clone_variant(self.context.store, self._variant, label=label.strip())
        self._variant = variant
        self.context.variants_changed.emit()
        self.context.status.emit(f"Created «{variant.label}».")

    def _save_stage(self) -> None:
        if self._variant is None or self._variant.is_shipped:
            return
        stage = self._current_stage()
        text = self.editors[stage].toPlainText()
        try:
            self._variant = update_variant_stage(
                self.context.store, self._variant, stage, text
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return
        self.context.variants_changed.emit()
        self.context.status.emit(f"Saved the {stage} prompt of «{self._variant.label}».")

    def _revert_stage(self) -> None:
        if self._variant is None or self._variant.is_shipped:
            return
        stage = self._current_stage()
        if stage not in self._variant.overridden_stages:
            return
        try:
            self._variant = update_variant_stage(
                self.context.store, self._variant, stage, ""
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot revert", str(exc))
            return
        self.context.variants_changed.emit()

    def _show_diff(self) -> None:
        if self._variant is None:
            return
        stage = self._current_stage()
        diff = variant_diff(self._variant, stage)
        QMessageBox.information(
            self,
            f"{stage} vs shipped",
            diff or "This stage is identical to the shipped prompt.",
        )

    def _delete(self) -> None:
        if self._variant is None or self._variant.is_shipped:
            return
        answer = QMessageBox.question(
            self, "Delete variant", f"Delete «{self._variant.label}»?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.context.store.delete_variant(
            self._variant.style_id, self._variant.variant_id
        )
        self._variant = None
        self.context.variants_changed.emit()

    # The lab's own prompts

    def _lab_page(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)

        column.addWidget(heading("The lab's own prompts"))
        column.addWidget(
            hint(
                "These drive the generator, the judge, and the optimizer. Saving "
                "writes the file in the package, so changes survive a restart."
            )
        )

        row = QHBoxLayout()
        self.lab_selector = QComboBox()
        for name in LAB_PROMPT_FILENAMES:
            self.lab_selector.addItem(LAB_PROMPT_LABELS.get(name, name), name)
        self.lab_selector.currentIndexChanged.connect(self._load_lab_prompt)
        row.addWidget(self.lab_selector, 1)
        save = QPushButton("Save to file")
        save.clicked.connect(self._save_lab_prompt)
        row.addWidget(save)
        reload_button = QPushButton("Reload from disk")
        reload_button.clicked.connect(self._reload_lab_prompts)
        row.addWidget(reload_button)
        column.addLayout(row)

        self.lab_editor = QPlainTextEdit()
        monospace(self.lab_editor)
        column.addWidget(self.lab_editor, 1)
        self._load_lab_prompt()
        return page

    def _load_lab_prompt(self) -> None:
        name = str(self.lab_selector.currentData())
        try:
            self.lab_editor.setPlainText(get_lab_prompt(name))
        except (KeyError, FileNotFoundError) as exc:
            self.lab_editor.setPlainText(f"Could not load this prompt: {exc}")

    def _save_lab_prompt(self) -> None:
        name = str(self.lab_selector.currentData())
        try:
            path = save_lab_prompt(name, self.lab_editor.toPlainText())
        except (KeyError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return
        self.context.status.emit(f"Saved {path.name}.")

    def _reload_lab_prompts(self) -> None:
        try:
            reload_lab_prompts()
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "Cannot reload", str(exc))
            return
        self._load_lab_prompt()
        self.context.status.emit("Reloaded the lab prompts from disk.")
