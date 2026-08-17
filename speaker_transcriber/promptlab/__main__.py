"""Launch the Prompt Lab on its own: `python -m speaker_transcriber.promptlab`."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    from speaker_transcriber.qt_interrupt import (
        INTERRUPT_EXIT_CODE,
        exec_with_interrupt_handling,
        install_interrupt_handling,
        is_interrupt_requested,
    )
    from speaker_transcriber.ui.branding import (
        apply_application_identity,
        configure_process_identity,
    )

    try:
        configure_process_identity()
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        application = QApplication(sys.argv)
        application.setOrganizationName("SpeakerTranscriber")
        apply_application_identity(application)
        install_interrupt_handling(application)

        from speaker_transcriber.ui.theme import apply_application_theme

        apply_application_theme(application)

        from speaker_transcriber.logging_config import configure_logging

        configure_logging()

        try:
            from speaker_transcriber.prompts import load_prompts
            from speaker_transcriber.promptlab.lab_prompts import load_lab_prompts

            load_prompts()
            load_lab_prompts()
        except FileNotFoundError as exc:
            QMessageBox.critical(None, "Prompt Lab", f"Could not load prompts:\n\n{exc}")
            return 1

        from speaker_transcriber.ui.promptlab_window import PromptLabWindow

        window = PromptLabWindow()
        window.show()
        if is_interrupt_requested(application):
            window.close()
            return INTERRUPT_EXIT_CODE
        return exec_with_interrupt_handling(application.exec, application)
    except KeyboardInterrupt:
        return INTERRUPT_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
