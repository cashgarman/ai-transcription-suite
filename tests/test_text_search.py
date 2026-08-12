from PySide6.QtWidgets import QApplication, QTextEdit

from speaker_transcriber.ui.text_search import TextFinder


def _application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_text_finder_matches_case_insensitively() -> None:
    _application()
    edit = QTextEdit()
    edit.setPlainText("Hello world. hello there. HELLO")
    finder = TextFinder()
    finder.set_query(edit.document(), "hello")
    assert len(finder.matches) == 3
    current, total = finder.status()
    assert total == 3
    assert current == 1


def test_text_finder_goto_wraps_and_empty_query_clears() -> None:
    _application()
    edit = QTextEdit()
    edit.setPlainText("alpha beta alpha")
    finder = TextFinder()
    finder.set_query(edit.document(), "alpha")
    first = finder.current_cursor()
    assert first is not None
    second = finder.goto(1)
    assert second is not None
    assert second.selectionStart() > first.selectionStart()
    wrapped = finder.goto(1)
    assert wrapped is not None
    assert wrapped.selectionStart() == first.selectionStart()
    finder.set_query(edit.document(), "")
    assert finder.matches == []
    assert finder.status() == (0, 0)
