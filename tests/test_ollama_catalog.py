from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from speaker_transcriber.models.model_catalog import (
    PINNED_OLLAMA_MODELS,
    ProgressTqdm,
    bind_progress_tqdm,
    aggregate_pull_progress,
    disk_usage_for,
    format_eta,
    ollama_models_dir,
    parse_size_label,
    whisper_display_name,
    whisper_repo_id,
    whisper_runtime_id,
)
from speaker_transcriber.models.ollama_catalog import (
    OllamaCatalogProvider,
    parse_ollama_cli_search,
    parse_ollama_library_size,
    parse_ollama_search_html,
    parse_ollama_search_json,
    parse_ollama_tags_html,
)
from speaker_transcriber.ui.model_combo import ComboModelItem, ModelComboBox


def _application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_whisper_runtime_id_maps_openai_repo() -> None:
    assert whisper_runtime_id("openai/whisper-large-v3") == "large-v3"
    assert whisper_runtime_id("Systran/faster-whisper-large-v3") == "large-v3"
    assert whisper_runtime_id("large-v3") == "large-v3"
    assert whisper_repo_id("openai/whisper-large-v3") == "Systran/faster-whisper-large-v3"
    assert whisper_display_name("large-v3") == "whisper-large-v3 (OpenAI)"


def test_parse_size_label() -> None:
    assert parse_size_label("6.6GB") == 6_600_000_000
    assert parse_size_label("398MB") == 398_000_000
    assert parse_size_label("no size") is None


def test_parse_ollama_search_html_extracts_library_names() -> None:
    html = """
    <ul role="list">
      <li><a href="/library/llama3.2"><h2>llama3.2</h2></a></li>
      <li><a href="/library/qwen2.5"><h2>qwen2.5</h2></a></li>
    </ul>
    """
    names = [entry.name for entry in parse_ollama_search_html(html)]
    assert names == ["llama3.2", "qwen2.5"]


def test_parse_ollama_search_json() -> None:
    payload = {
        "models": [
            {"name": "llama3.2", "description": "small llama", "size": "2.0GB"},
            {"id": "library/qwen2.5", "size_bytes": 4_700_000_000},
        ]
    }
    entries = parse_ollama_search_json(payload)
    assert entries is not None
    assert [entry.name for entry in entries] == ["llama3.2", "qwen2.5"]
    assert entries[0].size_bytes == 2_000_000_000
    assert entries[1].size_bytes == 4_700_000_000


def test_parse_ollama_library_size_reads_latest_tag() -> None:
    html = """
    <p class="text-neutral-800">llama3.2:latest</p>
    <p class="flex text-neutral-500">2.0GB • 128K context window • Text</p>
    <p class="text-neutral-800">llama3.2:1b</p>
    <p class="flex text-neutral-500">1.3GB • 128K context window</p>
    """
    assert parse_ollama_library_size(html, "llama3.2") == 2_000_000_000


def test_parse_ollama_cli_search() -> None:
    output = "NAME\tSIZE\nllama3.2\t2.0 GB\nqwen2.5\t4.7GB\n"
    entries = parse_ollama_cli_search(output)
    assert [entry.name for entry in entries] == ["llama3.2", "qwen2.5"]
    assert entries[0].size_bytes == 2_000_000_000
    assert entries[1].size_bytes == 4_700_000_000


def test_aggregate_pull_progress_sums_layers() -> None:
    layers: dict[str, tuple[int, int]] = {}
    started = 0.0
    first = aggregate_pull_progress(
        layers,
        {"digest": "aaa", "completed": 50, "total": 100, "status": "downloading"},
        started,
    )
    second = aggregate_pull_progress(
        layers,
        {"digest": "bbb", "completed": 25, "total": 100, "status": "downloading"},
        started,
    )
    assert first.total_bytes == 100
    assert second.completed_bytes == 75
    assert second.total_bytes == 200
    assert second.percent == 38


def test_format_eta() -> None:
    assert format_eta(0) == "<1s"
    assert format_eta(12) == "12s"
    assert format_eta(75) == "1m 15s"


def test_ollama_models_dir_uses_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "models"))
    assert ollama_models_dir() == tmp_path / "models"


def test_disk_usage_for_missing_path(tmp_path) -> None:
    usage = disk_usage_for(tmp_path / "does-not-exist" / "models")
    assert usage.total_bytes > 0
    assert usage.free_bytes >= 0


def test_model_combo_sentinel_is_not_a_model_name() -> None:
    _application()
    combo = ModelComboBox()
    combo.set_items([ComboModelItem(value="large-v3", label="whisper-large-v3 (OpenAI)")])
    combo.select_preferred(["large-v3"])
    assert combo.current_value() == "large-v3"
    add_index = combo.count() - 1
    combo.setCurrentIndex(add_index)
    assert combo.current_value() == "large-v3"
    assert combo.current_model_name() == "large-v3"


def test_model_combo_inserts_separator_before_add_models() -> None:
    _application()
    combo = ModelComboBox()
    combo.set_items([ComboModelItem(value="large-v3", label="whisper-large-v3 (OpenAI)")])
    kinds = [
        combo.model().item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
        for row in range(combo.model().rowCount())
    ]
    assert kinds[-2] == "separator"
    assert kinds[-1] == "add"


def test_model_combo_greys_uninstalled_items() -> None:
    from PySide6.QtGui import QColor

    from speaker_transcriber.ui.theme import Theme

    _application()
    combo = ModelComboBox()
    combo.set_items(
        [
            ComboModelItem(value="large-v3", label="large-v3", installed=True),
            ComboModelItem(value="tiny", label="tiny", installed=False),
        ]
    )
    installed = combo.model().item(0, 0)
    missing = combo.model().item(1, 0)
    assert installed.data(Qt.ItemDataRole.UserRole + 2) is True
    assert missing.data(Qt.ItemDataRole.UserRole + 2) is False
    assert missing.foreground().color() == QColor(Theme.TEXT_MUTED)
    combo.set_items(
        [
            ComboModelItem(value="large-v3", label="large-v3", installed=True),
            ComboModelItem(value="tiny", label="tiny", installed=True),
        ]
    )
    restored = combo.model().item(1, 0)
    assert restored.data(Qt.ItemDataRole.UserRole + 2) is True
    assert restored.foreground().color() == QColor(Theme.TEXT)
    combo.select_preferred(["tiny"])
    assert combo.property("modelInstalled") == "true"


def test_progress_tqdm_reports_percent() -> None:
    updates = []
    bar = ProgressTqdm(total=100, on_progress=updates.append)
    bar.update(40)
    assert updates[-1].percent == 40
    assert updates[-1].completed_bytes == 40
    assert updates[-1].total_bytes == 100


def test_progress_tqdm_class_has_lock_api() -> None:
    updates: list = []
    tqdm_class = bind_progress_tqdm(updates.append, None)
    assert isinstance(tqdm_class, type)
    lock = tqdm_class.get_lock()
    tqdm_class.set_lock(lock)
    files = tqdm_class(total=3, desc="Fetching 3 files")
    files.update(1)
    assert updates == []
    bar = tqdm_class(total=100, unit="B", desc="Downloading bytes")
    bar.update(40)
    bar.refresh()
    assert updates[-1].percent == 40
    assert bar.format_dict.get("rate") is not None
    bar.set_postfix_str("1.2MB/s", refresh=False)
    assert bar.postfix == "1.2MB/s"
    assert list(tqdm_class([1, 2], desc="Fetching 2 files")) == [1, 2]


def test_ollama_provider_pins_recommended(monkeypatch) -> None:
    monkeypatch.setattr(
        "speaker_transcriber.models.ollama_catalog._installed_names",
        lambda: {"qwen3.5:9b"},
    )
    provider = OllamaCatalogProvider()
    monkeypatch.setattr(provider, "_fetch_search", lambda query: [])
    monkeypatch.setattr(
        "speaker_transcriber.models.ollama_catalog._cli_search",
        lambda query: [],
    )
    monkeypatch.setattr(
        "speaker_transcriber.models.ollama_catalog._fetch_family_size",
        lambda family: {
            "llama3.2": 2_000_000_000,
            "qwen2.5": 4_700_000_000,
        }.get(family),
    )
    entries = provider.list_models()
    names = [entry.name for entry in entries]
    assert names[:2] == [name for name, _role in PINNED_OLLAMA_MODELS]
    assert names[0] == "llama3.2"
    assert names[1] == "qwen2.5"
    assert entries[0].size_bytes == 2_000_000_000
    assert entries[1].size_bytes == 4_700_000_000


def test_sortable_table_item_orders_sizes_numerically() -> None:
    from speaker_transcriber.ui.add_models_dialog import SortableTableItem

    _application()
    smaller = SortableTableItem("~858 MB", 858_000_000)
    larger = SortableTableItem("1.9 GB", 1_900_000_000)
    missing = SortableTableItem("—", None)
    assert smaller < larger
    assert not (larger < smaller)
    assert smaller < missing
    assert larger < missing
    names = SortableTableItem("qwen2.5", "qwen2.5")
    earlier = SortableTableItem("llama3.2", "llama3.2")
    assert earlier < names


def test_add_models_dialog_hides_progress_when_download_completes(monkeypatch) -> None:
    from pathlib import Path

    from speaker_transcriber.models.model_catalog import DiskUsage
    from speaker_transcriber.ui.add_models_dialog import AddModelsDialog

    _application()

    class FakeProvider:
        title = "Test voices"
        id = "tts"

        def disk_usage(self):
            return DiskUsage(500_000_000_000, 1_000_000_000_000, Path("C:/"))

    monkeypatch.setattr(AddModelsDialog, "_run_search", lambda self: None)
    dialog = AddModelsDialog(FakeProvider())
    dialog.show()
    _application().processEvents()
    dialog._set_download_progress_active(True)
    _application().processEvents()

    assert dialog.progress.isVisible()
    assert dialog.progress_label.isVisible()
    assert dialog.eta_label.isVisible()
    assert dialog.progress.is_animating()

    dialog._on_download_completed()

    assert not dialog.progress.isVisible()
    assert not dialog.progress_label.isVisible()
    assert not dialog.eta_label.isVisible()
    assert not dialog.progress.is_animating()
    assert dialog.status.text() == "Download complete"
    dialog.close()
