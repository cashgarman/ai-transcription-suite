from __future__ import annotations

from pathlib import Path

p = Path(__file__).resolve().parents[1] / "speaker_transcriber" / "ui" / "main_window.py"
text = p.read_text(encoding="utf-8")

replacements = [
    (
        """    def _add_source_paths(self, paths: list[Path]) -> None:
        self.input_timeline.append_paths(paths)
        self._probe_durations(paths)
        self._remember_recent_files(paths)
        self._on_sources_changed()""",
        """    def _add_source_paths(self, paths: list[Path]) -> None:
        if not paths:
            return
        if not is_licensed():
            existing = self.input_timeline.paths()
            if existing:
                show_multi_file_upsell(self, self._open_license_dialog)
                return
            if len(paths) > 1:
                show_multi_file_upsell(self, self._open_license_dialog)
                paths = paths[:1]
        self.input_timeline.append_paths(paths)
        self._probe_durations(paths)
        self._remember_recent_files(paths)
        self._on_sources_changed()
        self._refresh_start_button_tooltip()""",
    ),
    (
        """    def _on_duration_ready(self, resolved_path: str, duration_seconds: float) -> None:
        self.input_timeline.set_duration(Path(resolved_path), duration_seconds)""",
        """    def _on_duration_ready(self, resolved_path: str, duration_seconds: float) -> None:
        self.input_timeline.set_duration(Path(resolved_path), duration_seconds)
        self._refresh_start_button_tooltip()""",
    ),
    (
        """        cached = self.transcript_cache.load(sources)
        if cached is None:
            return
        self._autoload_in_progress = True
        try:
            self._load_from_cache(cached, sources)""",
        """        cached = self.transcript_cache.load(sources)
        if cached is None:
            return
        if not self._trial_cache_allowed(sources, cached):
            return
        self._autoload_in_progress = True
        try:
            self._load_from_cache(cached, sources)""",
    ),
    (
        """    def _start(self) -> None:
        sources = self._validate_source_input()
        if sources is None:
            return
        if self.settings.use_cached_transcript:
            cached = self.transcript_cache.load(sources)
            if cached is not None:
                if self._displayed_source_key() != self._source_key(sources):
                    self._load_from_cache(cached, sources)
                return
        self._run_transcription(sources)""",
        """    def _start(self) -> None:
        sources = self._validate_source_input()
        if sources is None:
            return
        if self.settings.use_cached_transcript:
            cached = self.transcript_cache.load(sources)
            if cached is not None and self._trial_cache_allowed(sources, cached):
                if self._displayed_source_key() != self._source_key(sources):
                    self._load_from_cache(cached, sources)
                return
        if not is_licensed() and len(sources) == 1:
            full_duration = self.input_timeline.total_duration()
            if full_duration > TRIAL_MAX_DURATION_SECONDS:
                choice = show_truncation_offer(
                    self,
                    full_duration,
                    self._open_license_dialog,
                )
                if choice == "truncate":
                    self._run_transcription(
                        sources,
                        max_input_duration_seconds=TRIAL_MAX_DURATION_SECONDS,
                        source_duration_seconds=full_duration,
                    )
                return
        self._run_transcription(sources)""",
    ),
    (
        """    def _run_transcription(self, sources: list[Path]) -> None:
        options = self._processing_options()""",
        """    def _run_transcription(
        self,
        sources: list[Path],
        *,
        max_input_duration_seconds: float | None = None,
        source_duration_seconds: float | None = None,
    ) -> None:
        options = self._processing_options()
        options.max_input_duration_seconds = max_input_duration_seconds
        options.source_duration_seconds = source_duration_seconds""",
    ),
    (
        """        self.notifications.show_message("Transcription complete", kind="success")
        decisions = result.fallback_config.get("decisions", [])
        if decisions:
            self.log_output.appendPlainText("\\n".join(decisions))""",
        """        if result.fallback_config.get("trial_truncated"):
            source_duration = float(
                result.fallback_config.get("source_duration_seconds")
                or result.duration_seconds
            )
            self.notifications.show_message(
                partial_transcript_message(result.duration_seconds, source_duration),
                kind="info",
            )
        else:
            self.notifications.show_message("Transcription complete", kind="success")
        decisions = result.fallback_config.get("decisions", [])
        if decisions:
            self.log_output.appendPlainText("\\n".join(decisions))""",
    ),
    (
        """    def _on_failed(self, message: str) -> None:
        self._set_stage_status("Processing failed")
        self.log_output.appendPlainText(message)
        self.log_section.set_expanded(True)
        QMessageBox.critical(self, "Processing failed", message)
        self._set_busy(False)""",
        """    def _on_failed(self, message: str) -> None:
        self._set_stage_status("Processing failed")
        self.log_output.appendPlainText(message)
        self.log_section.set_expanded(True)
        if "multi-file merge is included in the Personal license" in message:
            show_multi_file_upsell(self, self._open_license_dialog)
        else:
            QMessageBox.critical(self, "Processing failed", message)
        self._set_busy(False)""",
    ),
]

for index, (old, new) in enumerate(replacements):
    if old not in text:
        raise SystemExit(f"replacement {index} not found")
    text = text.replace(old, new, 1)

insert_after = """    def _bind_find_shortcut(self) -> None:
        shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self._focus_current_tab_search)

    def _focus_current_tab_search(self) -> None:"""

insert_block = """    def _bind_find_shortcut(self) -> None:
        shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self._focus_current_tab_search)

    def _bind_dev_mode_shortcut(self) -> None:
        if not dev_tools_enabled():
            return
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_F12), self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self._toggle_dev_entitlement_mode)

    def _toggle_dev_entitlement_mode(self) -> None:
        toggle_dev_mode_override()
        self.notifications.show_message(
            f"Testing mode: {dev_mode_label()} (F12 to switch)",
            kind="info",
        )
        self._refresh_entitlement_ui()

    def _open_license_dialog(self) -> None:
        if prompt_import_license(self):
            self._refresh_entitlement_ui()

    def _refresh_entitlement_ui(self) -> None:
        licensed = is_licensed()
        self.trial_hint_label.setVisible(not licensed)
        self.entitlement_mode_label.setText(entitlements_mode_display())
        self._refresh_start_button_tooltip()

    def _refresh_start_button_tooltip(self) -> None:
        if is_licensed():
            self.start_button.setToolTip("")
            return
        duration = self.input_timeline.total_duration()
        if duration > TRIAL_MAX_DURATION_SECONDS:
            self.start_button.setToolTip(
                "Trial will offer to transcribe the first 10 minutes."
            )
        else:
            self.start_button.setToolTip("")

    def _trial_cache_allowed(
        self,
        sources: list[Path],
        cached: TranscriptResult,
    ) -> bool:
        if is_licensed():
            return True
        if len(sources) > 1:
            return False
        full_duration = self.input_timeline.total_duration()
        if full_duration <= TRIAL_MAX_DURATION_SECONDS:
            return True
        return (
            cached.duration_seconds <= TRIAL_MAX_DURATION_SECONDS
            or bool(cached.fallback_config.get("trial_truncated"))
        )

    def _focus_current_tab_search(self) -> None:"""

if insert_after not in text:
    raise SystemExit("insert block anchor missing")
text = text.replace(insert_after, insert_block, 1)

p.write_text(text, encoding="utf-8")
print("patched", p)
