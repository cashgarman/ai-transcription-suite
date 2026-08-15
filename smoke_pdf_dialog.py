"""Throwaway headless smoke test for the PDF export dialog."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from speaker_transcriber.export.pdf_options import COVER_PAGE_OPTION
from speaker_transcriber.export.pdf_theme import PDF_THEMES, palette_for
from speaker_transcriber.ui.pdf_options_dialog import PdfOptionsDialog


app = QApplication([])

dialog = PdfOptionsDialog(
    "meeting_summary", "sepia", {COVER_PAGE_OPTION: False}
)
assert dialog.windowTitle() == "Export PDF — Meeting Summary", dialog.windowTitle()
assert dialog.selected_theme() == "sepia"
assert [
    dialog.theme_combo.itemData(i) for i in range(dialog.theme_combo.count())
] == list(PDF_THEMES)

box = dialog._boxes[COVER_PAGE_OPTION]
assert not box.isChecked()
assert dialog.choices().options == {COVER_PAGE_OPTION: False}

dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("midnight"))
assert dialog.selected_theme() == "midnight"
assert dialog.preview._palette == palette_for("midnight", "meeting_summary")
assert "navy" in dialog._theme_description.text().lower()

dialog._restore_defaults()
assert dialog.selected_theme() == "light"
assert box.isChecked()

newsletter = PdfOptionsDialog("internal_newsletter", "slate")
assert newsletter._boxes == {}, "cover toggle should be hidden for a newsletter"
assert newsletter.choices().theme == "slate"

dialog.resize(520, dialog.sizeHint().height())
dialog.show()
app.processEvents()
dialog.grab().save("dialog_preview.png")
print("dialog OK; themes:", ", ".join(PDF_THEMES))
