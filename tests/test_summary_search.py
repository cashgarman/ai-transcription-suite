"""Search in the Summary tab, driven through the real widgets offscreen."""

from types import SimpleNamespace

import pytest

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QTextEdit

from speaker_transcriber.ui.detachable_tab_widget import DetachableTabWidget
from speaker_transcriber.ui.main_window import MainWindow
from speaker_transcriber.ui.text_search import SearchableTextPanel


SUMMARY = (
    "# Weekly Sync\n\n"
    "**Participants:** Cash, GranSeba\n\n"
    "## Determinism\n\n"
    "- Cash: the seed must be saved with every turn.\n"
    "- GranSeba: cosmetic rolls need no save state.\n\n"
    "## Action Items\n\n"
    "| Owner | Action | Priority |\n| --- | --- | --- |\n"
    "| Cash | Clear the derived data cache | High |\n"
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def make_panel(markdown: str = SUMMARY) -> SearchableTextPanel:
    view = QTextEdit()
    view.setMarkdown(markdown)
    panel = SearchableTextPanel(view, placeholder="Search summary…")
    panel.setObjectName("summaryPanel")
    return panel


def test_typing_in_the_search_bar_finds_matches(app: QApplication) -> None:
    panel = make_panel()
    panel.search_bar.set_query("Cash")
    assert panel.match_status() == (1, 3)
    panel.search_bar.set_query("determinism")
    assert panel.match_status() == (1, 1)
    panel.search_bar.set_query("nowhere in this document")
    assert panel.match_status() == (0, 0)


def test_replacing_the_document_keeps_the_query_working(app: QApplication) -> None:
    panel = make_panel()
    panel.search_bar.set_query("Cash")
    assert panel.match_status()[1] == 3

    panel.text_edit.setMarkdown(SUMMARY.replace("Cash", "Cassidy Grant"))
    panel.refresh_query()
    assert panel.match_status() == (0, 0)

    panel.search_bar.set_query("Cassidy")
    assert panel.match_status()[1] == 3


def test_streaming_text_is_searchable_as_it_arrives(app: QApplication) -> None:
    panel = make_panel("Generating summary…\n")
    panel.search_bar.set_query("shader")
    assert panel.match_status() == (0, 0)

    cursor = panel.text_edit.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText("- Cash: the shader compile step fails.\n")
    panel.text_edit.setTextCursor(cursor)

    assert panel.match_status() == (1, 1)


def test_clearing_the_search_drops_the_highlights(app: QApplication) -> None:
    panel = make_panel()
    panel.search_bar.set_query("Cash")
    assert panel.match_status()[1] == 3
    panel.clear_search()
    assert panel.match_status() == (0, 0)
    assert panel.search_bar.query() == ""


def make_window(app: QApplication) -> SimpleNamespace:
    """A stand-in with the attributes the search routing actually touches."""
    tabs = DetachableTabWidget()
    transcript_panel = make_panel("Cash: the shader step fails.")
    summary_panel = make_panel()
    tabs.add_detachable_tab(transcript_panel, "Transcript", tab_id="transcript")
    tabs.add_detachable_tab(summary_panel, "Summary", tab_id="summary")
    focused: list[str] = []
    transcript_panel.focus_search = lambda: focused.append("transcript")
    summary_panel.focus_search = lambda: focused.append("summary")
    window = SimpleNamespace(
        tabs=tabs,
        transcript_panel=transcript_panel,
        summary_panel=summary_panel,
        focused=focused,
    )
    window._searchable_panel = lambda widget: MainWindow._searchable_panel(window, widget)
    return window


def test_find_shortcut_follows_the_current_tab(app: QApplication) -> None:
    window = make_window(app)
    window.tabs.setCurrentWidget(window.summary_panel)
    MainWindow._focus_current_tab_search(window)
    assert window.focused == ["summary"]

    window.tabs.setCurrentWidget(window.transcript_panel)
    MainWindow._focus_current_tab_search(window)
    assert window.focused == ["summary", "transcript"]


def test_find_shortcut_reaches_a_detached_summary_tab(app: QApplication) -> None:
    """The tab shows a placeholder once detached, so Ctrl+F must not stop there."""
    window = make_window(app)
    window.tabs.detach("summary")
    assert window.tabs.currentWidget() is not window.summary_panel

    MainWindow._focus_current_tab_search(window)
    assert window.focused == ["summary"]


def test_find_shortcut_prefers_the_panel_holding_focus(app: QApplication) -> None:
    window = make_window(app)
    window.tabs.setCurrentWidget(window.transcript_panel)
    resolved = MainWindow._searchable_panel(window, window.summary_panel.text_edit)
    assert resolved is window.summary_panel
    assert MainWindow._searchable_panel(window, None) is None
    assert MainWindow._searchable_panel(window, window.tabs) is None


def test_loading_a_cached_transcript_clears_a_stale_query(app: QApplication) -> None:
    panel = make_panel()
    panel.search_bar.set_query("Cash")
    assert panel.match_status()[1] == 3

    calls: list[str] = []
    window = SimpleNamespace(
        result=None,
        summary_markdown=SUMMARY,
        summary_view=panel.text_edit,
        summary_panel=panel,
        transcript_panel=SimpleNamespace(clear=lambda: calls.append("transcript")),
        progress_bar=SimpleNamespace(setValue=lambda value: None),
        elapsed_label=SimpleNamespace(setText=lambda text: None),
        notifications=SimpleNamespace(show_message=lambda *args, **kwargs: None),
        _set_stage_status=lambda *args, **kwargs: None,
        _refresh_resource_meters=lambda: None,
        _show_result=lambda sources: calls.append("show"),
        _set_busy=lambda busy: None,
        _cache_status_message=lambda result, sources: "",
        _cache_notification_message=lambda result, sources: "",
    )
    MainWindow._load_from_cache(window, SimpleNamespace(source_name="a.wav"), [])

    assert calls == ["transcript", "show"]
    assert panel.search_bar.query() == ""
    assert panel.match_status() == (0, 0)


def test_a_finished_summary_is_searchable_immediately(app: QApplication) -> None:
    panel = make_panel("Generating summary…\n")
    panel.search_bar.set_query("Cash")
    assert panel.match_status() == (0, 0)

    window = SimpleNamespace(
        summary_markdown="",
        summary_view=panel.text_edit,
        summary_panel=panel,
        progress_bar=SimpleNamespace(setValue=lambda value: None),
        _named_summary_markdown=lambda text: text,
        _persist_summary=lambda text: None,
        _set_stage_status=lambda message: None,
        _set_busy=lambda busy: None,
    )
    MainWindow._summary_completed(window, SUMMARY)

    assert panel.match_status() == (1, 3)


def test_renaming_speakers_keeps_the_summary_searchable(app: QApplication) -> None:
    panel = make_panel()
    panel.search_bar.set_query("Cassidy")
    assert panel.match_status() == (0, 0)

    window = SimpleNamespace(
        summary_markdown="",
        summary_view=panel.text_edit,
        summary_panel=panel,
    )
    MainWindow._apply_summary_markdown(window, SUMMARY.replace("Cash", "Cassidy"))

    assert panel.match_status()[1] == 3
