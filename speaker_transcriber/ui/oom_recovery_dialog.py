from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.config import format_ctx_label


STOP = "stop"
RETRY = "retry"
REDUCE_CTX = "reduce_ctx"
SMALLER_MODEL = "smaller_model"


@dataclass(frozen=True)
class OomRecoveryRequest:
    """What the notes worker was doing when Ollama ran out of memory."""

    model_name: str
    num_ctx: int
    message: str = ""
    reduced_num_ctx: int | None = None
    smaller_model: str = ""


@dataclass(frozen=True)
class OomRecoveryChoice:
    action: str = STOP
    num_ctx: int | None = None
    model_name: str = ""
    always: bool = False


class GpuMemoryRecoveryDialog(QDialog):
    """Modal recovery options shown when notes generation runs out of GPU memory."""

    def __init__(self, request: OomRecoveryRequest, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.request = request
        self.setWindowTitle("GPU out of memory")
        self.setModal(True)
        self.setMinimumWidth(520)

        self._options: list[tuple[QRadioButton, str, QCheckBox | None]] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        headline = QLabel(
            "The GPU ran out of memory while writing meeting notes.\n"
            f"Model: {request.model_name or 'unknown'}    "
            f"Notes context: {format_ctx_label(request.num_ctx)}"
        )
        headline.setWordWrap(True)
        layout.addWidget(headline)

        if request.message:
            detail = QLabel(request.message.strip())
            detail.setWordWrap(True)
            detail.setObjectName("oomDetail")
            layout.addWidget(detail)

        prompt = QLabel("Choose how to continue:")
        prompt.setWordWrap(True)
        layout.addWidget(prompt)

        if request.reduced_num_ctx:
            self._add_option(
                layout,
                REDUCE_CTX,
                f"Lower Notes context to {format_ctx_label(request.reduced_num_ctx)} and retry",
                allow_always=True,
            )
        if request.smaller_model:
            self._add_option(
                layout,
                SMALLER_MODEL,
                f"Switch to {request.smaller_model} and retry",
                allow_always=True,
            )
        self._add_option(
            layout,
            RETRY,
            "Retry with the same settings (after freeing GPU memory)",
            allow_always=False,
        )
        self._add_option(
            layout,
            STOP,
            "Stop writing notes and keep what was already written",
            allow_always=False,
        )

        if self._options:
            self._options[0][0].setChecked(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continue")
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _add_option(
        self,
        layout: QVBoxLayout,
        action: str,
        label: str,
        allow_always: bool,
    ) -> None:
        button = QRadioButton(label)
        layout.addWidget(button)
        always: QCheckBox | None = None
        if allow_always:
            always = QCheckBox("Always use this option")
            always.setEnabled(False)
            always.setContentsMargins(24, 0, 0, 0)
            layout.addWidget(always, 0, Qt.AlignmentFlag.AlignLeft)
            button.toggled.connect(always.setEnabled)
            button.toggled.connect(
                lambda checked, box=always: None if checked else box.setChecked(False)
            )
        self._options.append((button, action, always))

    def selected_choice(self) -> OomRecoveryChoice:
        for button, action, always in self._options:
            if not button.isChecked():
                continue
            remember = bool(always is not None and always.isChecked())
            if action == REDUCE_CTX:
                return OomRecoveryChoice(
                    action=action,
                    num_ctx=self.request.reduced_num_ctx,
                    always=remember,
                )
            if action == SMALLER_MODEL:
                return OomRecoveryChoice(
                    action=action,
                    model_name=self.request.smaller_model,
                    always=remember,
                )
            return OomRecoveryChoice(action=action)
        return OomRecoveryChoice(action=STOP)


def ask_gpu_recovery(
    request: OomRecoveryRequest,
    parent: QWidget | None = None,
) -> OomRecoveryChoice:
    dialog = GpuMemoryRecoveryDialog(request, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return OomRecoveryChoice(action=STOP)
    return dialog.selected_choice()
