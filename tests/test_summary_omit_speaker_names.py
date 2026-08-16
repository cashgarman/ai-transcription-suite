from PySide6.QtWidgets import QApplication

from speaker_transcriber.ui.summary_sections_dialog import (
    SummarySectionsChoices,
    SummarySectionsDialog,
)
from speaker_transcriber.ui.worker import PdfExportWorker, SummarizationWorker


def _application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_summary_sections_dialog_shows_for_styles_without_sections() -> None:
    _application()
    dialog = SummarySectionsDialog("pure_transcription")
    assert dialog.omit_speaker_names_box is not None
    assert not dialog.omit_speaker_names_box.isChecked()
    dialog.close()


def test_summary_sections_dialog_restores_omit_names_default() -> None:
    _application()
    dialog = SummarySectionsDialog(
        "meeting_summary",
        omit_speaker_names=True,
    )
    dialog.omit_speaker_names_box.setChecked(True)
    dialog._restore_defaults()
    assert not dialog.omit_speaker_names_box.isChecked()
    dialog.close()


def test_summary_sections_dialog_returns_both_choices() -> None:
    _application()
    dialog = SummarySectionsDialog(
        "meeting_summary",
        ("action_items",),
        omit_speaker_names=True,
    )
    choices = dialog.choices()
    assert choices == SummarySectionsChoices(
        excluded_section_ids=("action_items",),
        omit_speaker_names=True,
    )
    dialog.close()


def test_summarization_worker_forwards_omit_speaker_names() -> None:
    worker = SummarizationWorker(
        "transcript",
        "test-model",
        8192,
        "meeting_summary",
        excluded_sections=("risks",),
        omit_speaker_names=True,
    )
    assert worker.omit_speaker_names is True
    assert worker.excluded_sections == ("risks",)


def test_pdf_export_worker_forwards_omit_speaker_names(tmp_path) -> None:
    worker = PdfExportWorker(
        str(tmp_path / "notes.pdf"),
        "transcript",
        style="meeting_summary",
        excluded_sections=("action_items",),
        omit_speaker_names=True,
    )
    assert worker.omit_speaker_names is True
    assert worker.excluded_sections == ("action_items",)
