import pytest
from PySide6.QtWidgets import QApplication

from speaker_transcriber.promptlab.store import LabStore
from speaker_transcriber.promptlab.types import GeneratedTranscript, SummaryRun


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(application, tmp_path, monkeypatch):
    """A Prompt Lab window rooted in a temporary store, with no Ollama calls."""
    from speaker_transcriber.ui import promptlab_window as module

    monkeypatch.setattr(module, "LabStore", lambda: LabStore(tmp_path / "lab"))
    monkeypatch.setattr(module.PromptLabWindow, "_load_models", lambda self: None)

    lab = module.PromptLabWindow()
    yield lab
    lab.runner.stop()
    lab.runner.wait(3000)
    lab.close()


def _seed(store: LabStore) -> None:
    from speaker_transcriber.promptlab.generator import GenerationSettings, generate_transcript
    from speaker_transcriber.promptlab.scenarios import build_scenario

    from promptlab_fakes import FakeOllamaClient

    scenario = build_scenario(61, kind_id="team_sync", duration_minutes=20)
    store.scenarios.save(scenario)
    dialogue = "\n".join(
        f"{person.name}: A sentence with enough words to be worth transcribing."
        for person in scenario.participants
    )
    transcript = generate_transcript(
        scenario,
        GenerationSettings("gen-model"),
        client=FakeOllamaClient(lambda kwargs: dialogue),
    )
    store.transcripts.save(transcript)
    store.runs.save(
        SummaryRun(
            run_id="run-1",
            transcript_id=transcript.transcript_id,
            scenario_id=scenario.scenario_id,
            variant_id="shipped",
            variant_fingerprint="f",
            style_id=transcript.style_id,
            model_name="m",
            num_ctx=8192,
            markdown="# Notes\n\n## Executive Summary\n\nIt went fine.",
        )
    )


def test_the_window_builds_all_six_tabs(window):
    assert window.tabs.count() == 6
    assert [window.tabs.tabText(index) for index in range(6)] == [
        "1. Transcripts",
        "2. Runs",
        "3. Judge",
        "4. A/B",
        "5. Optimize",
        "Prompts",
    ]


def test_the_tabs_start_empty_without_crashing(window):
    assert window.transcripts_tab.table.rowCount() == 0
    assert window.runs_tab.run_table.rowCount() == 0
    assert window.judge_tab.table.rowCount() == 0


def test_stored_records_populate_the_tables(window):
    _seed(window.context.store)
    window.context.transcripts_changed.emit()
    window.context.runs_changed.emit()

    assert window.transcripts_tab.table.rowCount() == 1
    assert window.runs_tab.transcript_table.rowCount() == 1
    assert window.runs_tab.run_table.rowCount() == 1


def test_selecting_a_transcript_shows_its_ground_truth(window):
    _seed(window.context.store)
    window.context.transcripts_changed.emit()
    window.transcripts_tab.table.selectRow(0)

    truth = window.transcripts_tab.truth_view.toPlainText()

    assert "Facts the notes must carry" in truth
    assert "Participants" in truth


def test_selecting_a_run_previews_its_markdown(window):
    _seed(window.context.store)
    window.context.runs_changed.emit()
    window.runs_tab.run_table.selectRow(0)

    assert "It went fine." in window.runs_tab.preview.toPlainText()


def test_the_leaderboard_lists_the_shipped_variant(window):
    _seed(window.context.store)
    window.optimize_tab.refresh()

    labels = [
        window.optimize_tab.table.item(row, 0).text()
        for row in range(window.optimize_tab.table.rowCount())
    ]

    assert any("Shipped" in label for label in labels)


def test_the_prompts_tab_loads_the_shipped_variant_read_only(window):
    tab = window.prompts_tab
    assert tab.variant_list.count() >= 1
    assert tab.editors["system"].toPlainText().strip()
    assert tab.editors["system"].isReadOnly()


def test_the_prompts_tab_shows_the_labs_own_prompts(window):
    text = window.prompts_tab.lab_editor.toPlainText()
    assert "dialogue" in text.lower()


def test_the_ab_tab_reports_an_empty_queue(window):
    assert "No pairs waiting" in window.ab_tab.queue_label.text()
    assert "Judge agreement" in window.ab_tab.agreement_label.text()


def _seed_pair(window):
    from speaker_transcriber.promptlab.ab import build_pairs

    store = window.context.store
    _seed(store)
    transcript = store.transcripts.all()[0]
    store.runs.save(
        SummaryRun(
            run_id="run-2",
            transcript_id=transcript.transcript_id,
            scenario_id=transcript.scenario_id,
            variant_id="var-rival",
            variant_fingerprint="g",
            style_id=transcript.style_id,
            model_name="m",
            num_ctx=8192,
            markdown="# Notes\n\n## Executive Summary\n\nA rival summary.",
        )
    )
    window.ab_tab.style_selector.setCurrentIndex(
        window.ab_tab.style_selector.findData(transcript.style_id)
    )
    build_pairs(store, "shipped", "var-rival", style_id=transcript.style_id)
    window.ab_tab.refresh()


def test_a_built_pair_shows_both_sides_blinded(window):
    _seed_pair(window)

    assert "1 pair(s) waiting" in window.ab_tab.queue_label.text()
    assert window.ab_tab.left_view.toPlainText().strip()
    assert window.ab_tab.right_view.toPlainText().strip()
    assert "shipped" not in window.ab_tab.left_label.text()
    assert "var-rival" not in window.ab_tab.right_label.text()


def test_a_number_key_records_a_verdict(window):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    _seed_pair(window)
    pair_id = window.ab_tab._current.pair_id

    window.ab_tab.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier, "1")
    )

    verdict = window.context.store.verdicts.get(pair_id)
    assert verdict is not None
    assert verdict.winner == "left"
    assert "No pairs waiting" in window.ab_tab.queue_label.text()


def test_keys_typed_into_the_notes_box_are_not_votes(window):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication as App

    _seed_pair(window)
    window.ab_tab.notes.setFocus()
    App.processEvents()

    App.sendEvent(
        window.ab_tab.notes,
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_1, Qt.KeyboardModifier.NoModifier, "1"),
    )

    assert window.ab_tab.notes.toPlainText() == "1"
    assert window.context.store.verdicts.count() == 0


def test_a_previewed_scenario_reaches_the_ground_truth_pane(window):
    window.transcripts_tab._preview()
    assert "Topics" in window.transcripts_tab.truth_view.toPlainText()


def test_generating_without_a_model_does_not_queue_anything(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    window.transcripts_tab.model.setCurrentText("")

    window.transcripts_tab._generate(1)

    assert window.runner.depth == 0


def test_generating_queues_one_job_per_transcript(window):
    window.transcripts_tab.model.setCurrentText("gen-model")

    window.transcripts_tab._generate(3)

    assert window.runner.depth == 3
    window.runner.cancel_all()


def test_status_messages_reach_the_strip(window):
    window.context.status.emit("Something happened.")
    assert window.job_label.text() == "Something happened."
