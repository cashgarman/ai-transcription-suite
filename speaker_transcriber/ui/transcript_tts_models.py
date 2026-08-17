from __future__ import annotations

import sys

from PySide6.QtWidgets import QWidget

from speaker_transcriber.config import AppSettings, SettingsStore
from speaker_transcriber.models.tts_catalog import (
    DEFAULT_TTS_MODEL,
    PIPER_VOICE_CATALOG,
    TtsCatalogProvider,
    WINDOWS_TTS_MODEL,
    is_piper_voice_installed,
)
from speaker_transcriber.ui.add_models_dialog import AddModelsDialog
from speaker_transcriber.ui.model_combo import ComboModelItem, ModelComboBox, combo_item_from_catalog


def tts_combo_items(settings: AppSettings) -> list[ComboModelItem]:
    provider = TtsCatalogProvider()
    items: list[ComboModelItem] = []
    seen: set[str] = set()

    if sys.platform == "win32":
        items.append(
            combo_item_from_catalog(provider.entry_for(WINDOWS_TTS_MODEL), vram=False)
        )
        seen.add(WINDOWS_TTS_MODEL)

    for spec in PIPER_VOICE_CATALOG:
        items.append(combo_item_from_catalog(provider.entry_for(spec.voice_id), vram=False))
        seen.add(spec.voice_id)

    for voice_id in settings.extra_tts_models:
        if voice_id in seen:
            continue
        items.append(combo_item_from_catalog(provider.entry_for(voice_id), vram=False))
        seen.add(voice_id)

    return items


def populate_tts_model_combo(combo: ModelComboBox, settings: AppSettings) -> None:
    combo.blockSignals(True)
    combo.set_items(tts_combo_items(settings))
    preferred = [settings.tts_model, DEFAULT_TTS_MODEL]
    if sys.platform == "win32":
        preferred.append(WINDOWS_TTS_MODEL)
    preferred.append(PIPER_VOICE_CATALOG[0].voice_id)
    combo.select_preferred(preferred)
    combo.blockSignals(False)


def open_add_tts_models_dialog(
    parent: QWidget,
    settings_store: SettingsStore,
) -> list[str]:
    settings = settings_store.load()
    dialog = AddModelsDialog(
        TtsCatalogProvider(settings_store.get_hf_token()),
        parent,
        token=settings_store.get_hf_token(),
    )
    dialog.exec()
    downloaded = dialog.downloaded_names()
    if not downloaded:
        return []
    extras = list(settings.extra_tts_models)
    changed = False
    for voice_id in downloaded:
        if voice_id == WINDOWS_TTS_MODEL:
            continue
        if voice_id not in extras and voice_id not in {
            spec.voice_id for spec in PIPER_VOICE_CATALOG
        }:
            extras.append(voice_id)
            changed = True
    if changed:
        settings.extra_tts_models = extras
    settings.tts_model = downloaded[-1]
    settings_store.save(settings)
    return downloaded


def selected_tts_model_requires_download(model_id: str | None) -> bool:
    if not model_id or model_id == WINDOWS_TTS_MODEL:
        return False
    return not is_piper_voice_installed(model_id)
