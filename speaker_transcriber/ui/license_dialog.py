from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from speaker_transcriber.entitlements import import_license


def prompt_import_license(parent: QWidget) -> bool:
    path_text, _ = QFileDialog.getOpenFileName(
        parent,
        "Import Summit license",
        "",
        "Summit license (*.summit);;All files (*.*)",
    )
    if not path_text:
        return False
    try:
        destination = import_license(Path(path_text))
    except ValueError as exc:
        QMessageBox.warning(parent, "Invalid license", str(exc))
        return False
    QMessageBox.information(
        parent,
        "License activated",
        f"Personal license installed for offline use:\n{destination}",
    )
    return True
