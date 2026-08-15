"""Throwaway: render every theme preview in one image for a visual check."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from speaker_transcriber.export.pdf_theme import PDF_THEME_CHOICES, palette_for
from speaker_transcriber.ui.pdf_options_dialog import ThemePreview


app = QApplication([])

window = QWidget()
window.setStyleSheet("background: #808080;")
layout = QVBoxLayout(window)
for entry in PDF_THEME_CHOICES:
    layout.addWidget(ThemePreview(palette_for(entry.theme_id, "meeting_summary")))
window.resize(420, 104 * len(PDF_THEME_CHOICES) + 60)
window.show()
app.processEvents()
window.grab().save("theme_grid.png")
print("wrote theme_grid.png for", len(PDF_THEME_CHOICES), "themes")
