from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from speaker_transcriber.config import AppSettings, SettingsStore, license_file_path
from speaker_transcriber.ui.license_dialog import prompt_import_license


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        store: SettingsStore,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.store = store
        self.setWindowTitle("Summit Settings")
        self.setMinimumWidth(480)

        self.compute_type = QComboBox()
        self.compute_type.addItems(["int8_float16", "float16", "int8", "float32"])
        self.compute_type.setCurrentText(settings.compute_type)
        self.batch_size = QSpinBox()
        self.batch_size.setRange(1, 64)
        self.batch_size.setValue(settings.batch_size)
        self.alignment_device = QComboBox()
        self.alignment_device.addItems(["cuda", "cpu"])
        self.alignment_device.setCurrentText(settings.alignment_device)
        self.diarization_device = QComboBox()
        self.diarization_device.addItems(["cuda", "cpu"])
        self.diarization_device.setCurrentText(settings.diarization_device)
        self.merge_gap = QDoubleSpinBox()
        self.merge_gap.setRange(0.0, 10.0)
        self.merge_gap.setDecimals(2)
        self.merge_gap.setValue(settings.merge_gap_seconds)
        self.max_duration = QDoubleSpinBox()
        self.max_duration.setRange(1.0, 300.0)
        self.max_duration.setValue(settings.max_block_duration_seconds)
        self.inherit_threshold = QDoubleSpinBox()
        self.inherit_threshold.setRange(0.0, 10.0)
        self.inherit_threshold.setDecimals(2)
        self.inherit_threshold.setValue(settings.inherit_speaker_threshold_seconds)
        self.output_directory = QLineEdit(settings.output_directory)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_directory)
        output_row.addWidget(browse)
        self.hf_token = QLineEdit()
        self.hf_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.hf_token.setPlaceholderText(
            "Leave blank to retain the token in the OS credential store"
        )
        self.use_cached_transcript = QCheckBox()
        self.use_cached_transcript.setChecked(settings.use_cached_transcript)
        self.license_status = QLabel()
        self._refresh_license_status()
        import_license = QPushButton("Import license…")
        import_license.clicked.connect(self._import_license)
        license_row = QHBoxLayout()
        license_row.addWidget(self.license_status, 1)
        license_row.addWidget(import_license)

        form = QFormLayout()
        form.addRow("Compute type", self.compute_type)
        form.addRow("Batch size", self.batch_size)
        form.addRow("Alignment device", self.alignment_device)
        form.addRow("Diarization device", self.diarization_device)
        form.addRow("Merge gap (seconds)", self.merge_gap)
        form.addRow("Maximum block duration", self.max_duration)
        form.addRow("Nearest-speaker threshold", self.inherit_threshold)
        form.addRow("Output directory", output_row)
        form.addRow("Hugging Face token", self.hf_token)
        form.addRow("Use cached transcript", self.use_cached_transcript)
        form.addRow("License", license_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select output directory",
            self.output_directory.text(),
        )
        if directory:
            self.output_directory.setText(directory)

    def _refresh_license_status(self) -> None:
        path = license_file_path()
        if path.is_file():
            self.license_status.setText(f"Personal license installed ({path.name})")
        else:
            self.license_status.setText("Trial mode (no license file)")

    def _import_license(self) -> None:
        if prompt_import_license(self):
            self._refresh_license_status()

    def _save(self) -> None:
        self.settings.compute_type = self.compute_type.currentText()
        self.settings.batch_size = self.batch_size.value()
        self.settings.alignment_device = self.alignment_device.currentText()
        self.settings.diarization_device = self.diarization_device.currentText()
        self.settings.merge_gap_seconds = self.merge_gap.value()
        self.settings.max_block_duration_seconds = self.max_duration.value()
        self.settings.inherit_speaker_threshold_seconds = self.inherit_threshold.value()
        self.settings.output_directory = self.output_directory.text().strip()
        self.settings.use_cached_transcript = self.use_cached_transcript.isChecked()
        token = self.hf_token.text().strip()
        try:
            if token:
                self.store.save_hf_token(token)
            self.store.save(self.settings)
        except Exception as exc:
            QMessageBox.critical(self, "Could not save settings", str(exc))
            return
        self.accept()
