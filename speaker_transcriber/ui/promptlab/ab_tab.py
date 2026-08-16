"""Blinded side-by-side comparison of two prompt variants.

Which variant produced which side stays hidden until a vote is cast. Knowing
that the left column is the shiny new candidate is enough to tilt a judgement,
and the whole point of asking a person is to get a signal the automatic scores
cannot supply.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.promptlab.ab import (
    build_pairs,
    judge_agreement,
    record_verdict,
)
from speaker_transcriber.promptlab.promptset import list_variants
from speaker_transcriber.promptlab.types import (
    ABPair,
    VERDICT_TAGS,
    WINNER_LEFT,
    WINNER_RIGHT,
    WINNER_TIE,
)
from speaker_transcriber.ui.promptlab.common import (
    LabContext,
    MarkdownView,
    heading,
    hint,
    style_combo,
)


TAG_LABELS = {
    "missed_facts": "Missed facts",
    "hallucinated": "Made things up",
    "wrong_owner": "Wrong owner",
    "too_long": "Too long",
    "too_terse": "Too terse",
    "bad_structure": "Bad structure",
    "weak_actions": "Weak action items",
    "tone_off": "Tone off",
}


class ABTab(QWidget):
    KEY_ACTIONS = {
        "1": WINNER_LEFT,
        "2": WINNER_TIE,
        "3": WINNER_RIGHT,
        "s": "skip",
    }

    def __init__(self, context: LabContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._queue: list[ABPair] = []
        self._current: ABPair | None = None
        self._build()
        self.context.runs_changed.connect(self._refresh_variants)
        self.context.variants_changed.connect(self._refresh_variants)
        self.context.verdicts_changed.connect(self.refresh)
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._setup_row())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_panel, self.left_view, self.left_label = _side_panel("A")
        self.right_panel, self.right_view, self.right_label = _side_panel("B")
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.right_panel)
        splitter.setSizes([600, 600])
        layout.addWidget(splitter, 1)

        layout.addWidget(self._verdict_row())

    def _setup_row(self) -> QWidget:
        frame = QFrame()
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self.style_selector = style_combo(self.context.settings.style_id)
        self.style_selector.currentIndexChanged.connect(self._refresh_variants)
        form.addRow("Style", self.style_selector)
        row.addLayout(form)

        pairing = QFormLayout()
        self.variant_a = QComboBox()
        self.variant_b = QComboBox()
        pairing.addRow("Variant A", self.variant_a)
        pairing.addRow("Variant B", self.variant_b)
        row.addLayout(pairing)

        buttons = QVBoxLayout()
        self.build_button = QPushButton("Build comparison queue")
        self.build_button.clicked.connect(self._build_pairs)
        buttons.addWidget(self.build_button)
        self.skip_button = QPushButton("Skip this pair")
        self.skip_button.clicked.connect(self._skip)
        buttons.addWidget(self.skip_button)
        row.addLayout(buttons)

        status = QVBoxLayout()
        self.queue_label = QLabel("No pairs waiting.")
        status.addWidget(self.queue_label)
        self.agreement_label = QLabel("")
        self.agreement_label.setWordWrap(True)
        status.addWidget(self.agreement_label)
        status.addWidget(
            hint(
                "Which variant wrote which side is hidden until you vote. "
                "Keys: 1 left, 2 tie, 3 right, S skip."
            )
        )
        row.addLayout(status, 1)
        return frame

    def _verdict_row(self) -> QWidget:
        box = QGroupBox("Your verdict")
        outer = QVBoxLayout(box)

        buttons = QHBoxLayout()
        self.left_button = QPushButton("◀  A is better  (1)")
        self.left_button.clicked.connect(lambda: self._vote(WINNER_LEFT))
        buttons.addWidget(self.left_button)
        self.tie_button = QPushButton("Tie  (2)")
        self.tie_button.clicked.connect(lambda: self._vote(WINNER_TIE))
        buttons.addWidget(self.tie_button)
        self.right_button = QPushButton("B is better  ▶  (3)")
        self.right_button.clicked.connect(lambda: self._vote(WINNER_RIGHT))
        buttons.addWidget(self.right_button)
        outer.addLayout(buttons)

        tags = QGridLayout()
        tags.addWidget(QLabel("What was wrong with the loser?"), 0, 0, 1, 4)
        self.tag_boxes: dict[str, QPushButton] = {}
        for index, tag in enumerate(VERDICT_TAGS):
            button = QPushButton(TAG_LABELS.get(tag, tag))
            button.setCheckable(True)
            self.tag_boxes[tag] = button
            tags.addWidget(button, 1 + index // 4, index % 4)
        outer.addLayout(tags)

        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(
            "What made the difference? These notes go straight to the optimizer, "
            "so be specific: 'dropped the deadline on the migration' beats 'worse'."
        )
        self.notes.setMaximumHeight(70)
        outer.addWidget(self.notes)
        return box

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Vote from the keyboard.

        Handled here rather than with a `QShortcut` so the notes box keeps its
        own keystrokes: a shortcut swallows the key before the focused widget
        ever sees it, which would make "1" and "S" untypeable.
        """
        action = self.KEY_ACTIONS.get(event.text().lower())
        if action is None:
            super().keyPressEvent(event)
            return
        event.accept()
        if action == "skip":
            self._skip()
        else:
            self._vote(action)

    # Data

    @property
    def style_id(self) -> str:
        return str(self.style_selector.currentData())

    def refresh(self) -> None:
        self._refresh_variants()
        self._reload_queue()
        agreement = judge_agreement(self.context.store, style_id=self.style_id)
        self.agreement_label.setText(f"Judge agreement: {agreement.summary}")

    def _refresh_variants(self) -> None:
        variants = list_variants(self.context.store, self.style_id)
        for combo, remembered in (
            (self.variant_a, self.context.settings.last_variant_a),
            (self.variant_b, self.context.settings.last_variant_b),
        ):
            chosen = combo.currentData() or remembered
            combo.blockSignals(True)
            combo.clear()
            for variant in variants:
                combo.addItem(variant.label, variant.variant_id)
            index = combo.findData(chosen)
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)
        if self.variant_b.count() > 1 and self.variant_b.currentIndex() == 0:
            self.variant_b.setCurrentIndex(1)

    def _reload_queue(self) -> None:
        self._queue = [
            pair
            for pair in self.context.store.unvoted_pairs()
            if pair.style_id == self.style_id
        ]
        self._queue.sort(key=lambda pair: pair.created_at)
        self._show_next()

    def _show_next(self) -> None:
        self._current = self._queue[0] if self._queue else None
        waiting = len(self._queue)
        self.queue_label.setText(
            f"{waiting} pair(s) waiting." if waiting else "No pairs waiting."
        )
        for tag_button in self.tag_boxes.values():
            tag_button.setChecked(False)
        self.notes.clear()

        if self._current is None:
            self.left_view.show_plain("")
            self.right_view.show_plain("")
            self.left_label.setText("A")
            self.right_label.setText("B")
            return

        left = self.context.store.runs.get(self._current.left_run_id)
        right = self.context.store.runs.get(self._current.right_run_id)
        transcript = self.context.store.transcripts.get(self._current.transcript_id)
        title = transcript.label if transcript else self._current.transcript_id
        self.left_label.setText(f"A — {title}")
        self.right_label.setText(f"B — {title}")
        self.left_view.show_markdown(left.markdown if left else "")
        self.right_view.show_markdown(right.markdown if right else "")

    # Actions

    def _build_pairs(self) -> None:
        first = str(self.variant_a.currentData() or "")
        second = str(self.variant_b.currentData() or "")
        if not first or not second or first == second:
            QMessageBox.information(
                self, "Pick two variants", "A comparison needs two different variants."
            )
            return
        self.context.settings.last_variant_a = first
        self.context.settings.last_variant_b = second
        self.context.save_settings()
        try:
            created = build_pairs(
                self.context.store, first, second, style_id=self.style_id
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot build pairs", str(exc))
            return
        if not created:
            QMessageBox.information(
                self,
                "Nothing to compare",
                "No transcript has a successful run from both variants yet. "
                "Run the matrix on the Runs tab first.",
            )
        self._reload_queue()
        self.context.status.emit(f"Built {len(created)} new comparison(s).")

    def _vote(self, winner: str) -> None:
        if self._current is None:
            return
        tags = tuple(tag for tag, button in self.tag_boxes.items() if button.isChecked())
        record_verdict(
            self.context.store,
            self._current.pair_id,
            winner,
            tags=tags,
            notes=self.notes.toPlainText(),
        )
        chose = (
            "a tie"
            if winner == WINNER_TIE
            else f"«{self._current.variant_id_for(winner)}»"
        )
        left = self._current.left_variant_id
        right = self._current.right_variant_id
        self._queue.pop(0)
        self.context.verdicts_changed.emit()
        self.context.status.emit(
            f"Recorded {chose}. That pair was A = {left}, B = {right}."
        )

    def _skip(self) -> None:
        if not self._queue:
            return
        self._queue.append(self._queue.pop(0))
        self._show_next()


def _side_panel(title: str) -> tuple[QWidget, MarkdownView, QLabel]:
    panel = QWidget()
    column = QVBoxLayout(panel)
    column.setContentsMargins(0, 0, 0, 0)
    label = heading(title)
    column.addWidget(label)
    view = MarkdownView()
    column.addWidget(view)
    return panel, view, label
