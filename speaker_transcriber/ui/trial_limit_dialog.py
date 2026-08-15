from __future__ import annotations

import webbrowser
from typing import Callable, Literal

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from speaker_transcriber.config import purchase_url
from speaker_transcriber.entitlements import multi_file_error_message
from speaker_transcriber.export.common import clock_timestamp

TruncationChoice = Literal["truncate", "upgrade", "license", "cancel"]


def open_purchase_page() -> None:
    url = QUrl(purchase_url())
    if not QDesktopServices.openUrl(url):
        webbrowser.open(purchase_url())


def show_multi_file_upsell(
    parent: QWidget,
    on_enter_license: Callable[[], None] | None = None,
) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Multiple files require a license")
    layout = QVBoxLayout(dialog)
    layout.addWidget(
        QLabel(
            multi_file_error_message()
            + "\n\nUpgrade to Personal for multi-file merge and unlimited recording length."
        )
    )
    buttons = QDialogButtonBox()
    upgrade = buttons.addButton("Upgrade to Personal", QDialogButtonBox.ButtonRole.ActionRole)
    license_button = buttons.addButton(
        "Enter license…",
        QDialogButtonBox.ButtonRole.ActionRole,
    )
    dismiss = buttons.addButton(
        "Keep using trial",
        QDialogButtonBox.ButtonRole.RejectRole,
    )
    upgrade.clicked.connect(lambda: (open_purchase_page(), dialog.done(0)))
    license_button.clicked.connect(
        lambda: (dialog.done(0), on_enter_license() if on_enter_license else None)
    )
    dismiss.clicked.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()


def show_truncation_offer(
    parent: QWidget,
    full_duration_seconds: float,
    on_enter_license: Callable[[], None] | None = None,
) -> TruncationChoice:
    full = clock_timestamp(full_duration_seconds)
    limit = clock_timestamp(600.0)
    dialog = QDialog(parent)
    dialog.setWindowTitle("Transcribe the first 10 minutes?")
    layout = QVBoxLayout(dialog)
    layout.addWidget(
        QLabel(
            f"This recording is {full}. The trial can transcribe the first {limit} so "
            "you can try speaker labels, notes, and exports on your real audio.\n\n"
            f"The transcript will cover 0:00–{limit} only, not the full meeting."
        )
    )
    buttons = QDialogButtonBox()
    truncate = buttons.addButton(
        "Transcribe first 10 minutes",
        QDialogButtonBox.ButtonRole.AcceptRole,
    )
    upgrade = buttons.addButton("Upgrade to Personal", QDialogButtonBox.ButtonRole.ActionRole)
    license_button = buttons.addButton(
        "Enter license…",
        QDialogButtonBox.ButtonRole.ActionRole,
    )
    cancel = buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
    choice: list[TruncationChoice] = ["cancel"]

    truncate.clicked.connect(lambda: (choice.__setitem__(0, "truncate"), dialog.accept()))
    upgrade.clicked.connect(
        lambda: (open_purchase_page(), choice.__setitem__(0, "upgrade"), dialog.accept())
    )

    def enter_license() -> None:
        choice[0] = "license"
        dialog.accept()
        if on_enter_license:
            on_enter_license()

    license_button.clicked.connect(enter_license)
    cancel.clicked.connect(lambda: (choice.__setitem__(0, "cancel"), dialog.reject()))
    layout.addWidget(buttons)
    dialog.exec()
    return choice[0]
