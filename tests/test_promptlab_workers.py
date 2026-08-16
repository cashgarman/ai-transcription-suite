import threading

import pytest
from PySide6.QtWidgets import QApplication

from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.models.summarization import OllamaOutOfMemoryError
from speaker_transcriber.promptlab.settings import LabSettings, LabSettingsStore
from speaker_transcriber.ui.oom_recovery_dialog import (
    OomRecoveryChoice,
    REDUCE_CTX,
    STOP,
)
from speaker_transcriber.ui.promptlab.workers import (
    KIND_GENERATE,
    JobContext,
    LabJob,
    LabJobRunner,
)


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def runner(application):
    worker = LabJobRunner()
    yield worker
    worker.stop()
    worker.wait(3000)


def _job(name: str, run, *, model_name: str = "m", num_ctx: int = 8192) -> LabJob:
    return LabJob(
        job_id=name,
        kind=KIND_GENERATE,
        label=name,
        model_name=model_name,
        num_ctx=num_ctx,
        run=run,
    )


def _drain(runner: LabJobRunner, timeout: float = 5.0) -> bool:
    """Wait for the queue to empty, pumping Qt events so signals are delivered."""
    done = threading.Event()
    runner.idle.connect(done.set)
    runner.start()
    deadline = timeout
    step = 0.02
    while deadline > 0 and not done.is_set():
        QApplication.processEvents()
        done.wait(step)
        deadline -= step
    QApplication.processEvents()
    return done.is_set()


def test_jobs_run_one_at_a_time_in_order(runner):
    order: list[str] = []
    overlapping: list[bool] = []
    active = threading.Lock()

    def work(name):
        def run(context: JobContext) -> str:
            acquired = active.acquire(blocking=False)
            overlapping.append(not acquired)
            order.append(name)
            if acquired:
                active.release()
            return name

        return run

    for index in range(4):
        runner.enqueue(_job(f"job-{index}", work(f"job-{index}")))

    assert _drain(runner)
    assert order == ["job-0", "job-1", "job-2", "job-3"]
    assert not any(overlapping)


def test_the_queue_depth_is_reported(runner):
    seen: list[int] = []
    runner.queue_changed.connect(seen.append)

    for index in range(3):
        runner.enqueue(_job(f"job-{index}", lambda context: None))

    assert seen[:3] == [1, 2, 3]
    assert _drain(runner)
    assert runner.depth == 0


def test_a_result_is_delivered_with_its_job_id(runner):
    results: list[tuple[str, object]] = []
    runner.job_finished.connect(
        lambda job_id, kind, value: results.append((job_id, value))
    )

    runner.enqueue(_job("job-1", lambda context: {"answer": 42}))

    assert _drain(runner)
    assert results == [("job-1", {"answer": 42})]


def test_a_failing_job_reports_and_the_queue_continues(runner):
    failures: list[tuple[str, str]] = []
    finished: list[str] = []
    runner.job_failed.connect(lambda job_id, message: failures.append((job_id, message)))
    runner.job_finished.connect(
        lambda job_id, kind, value: finished.append(job_id)
    )

    def explode(context: JobContext):
        raise RuntimeError("nope")

    runner.enqueue(_job("bad", explode))
    runner.enqueue(_job("good", lambda context: "fine"))

    assert _drain(runner)
    assert failures == [("bad", "nope")]
    assert finished == ["good"]


def test_a_cancelled_job_is_reported_as_cancelled(runner):
    cancelled: list[str] = []
    runner.job_cancelled.connect(cancelled.append)

    def bail(context: JobContext):
        raise ProcessingCancelled()

    runner.enqueue(_job("job-1", bail))

    assert _drain(runner)
    assert cancelled == ["job-1"]


def test_cancel_all_drops_queued_jobs(runner):
    started = threading.Event()
    release = threading.Event()
    ran: list[str] = []

    def blocker(context: JobContext):
        started.set()
        release.wait(2.0)
        context.raise_if_cancelled()
        return "done"

    def later(context: JobContext):
        ran.append("later")
        return None

    runner.enqueue(_job("blocker", blocker))
    runner.enqueue(_job("later", later))
    runner.start()
    assert started.wait(3.0)

    runner.cancel_all()
    release.set()

    deadline = 3.0
    while deadline > 0 and runner.depth:
        QApplication.processEvents()
        threading.Event().wait(0.02)
        deadline -= 0.02
    QApplication.processEvents()

    assert ran == []


def test_progress_and_chunks_are_forwarded(runner):
    progress: list[tuple[str, float, str]] = []
    chunks: list[tuple[str, str]] = []
    runner.job_progress.connect(
        lambda job_id, fraction, message: progress.append((job_id, fraction, message))
    )
    runner.job_chunk.connect(lambda job_id, text: chunks.append((job_id, text)))

    def work(context: JobContext):
        context.progress(0.5, "halfway")
        context.chunk("some text")
        return None

    runner.enqueue(_job("job-1", work))

    assert _drain(runner)
    assert progress == [("job-1", 0.5, "halfway")]
    assert chunks == [("job-1", "some text")]


def test_out_of_memory_pauses_and_retries_with_a_smaller_context(runner):
    attempts: list[int] = []

    def flaky(context: JobContext):
        attempts.append(context.num_ctx)
        if len(attempts) == 1:
            raise OllamaOutOfMemoryError("out of memory")
        return "recovered"

    runner.oom_detected.connect(
        lambda request: runner.provide_recovery(
            OomRecoveryChoice(action=REDUCE_CTX, num_ctx=4096)
        )
    )
    finished: list[object] = []
    runner.job_finished.connect(
        lambda job_id, kind, value: finished.append(value)
    )

    runner.enqueue(_job("job-1", flaky, num_ctx=8192))

    assert _drain(runner)
    assert attempts == [8192, 4096]
    assert finished == ["recovered"]


def test_choosing_stop_after_out_of_memory_cancels_the_job(runner):
    cancelled: list[str] = []
    runner.job_cancelled.connect(cancelled.append)
    runner.oom_detected.connect(
        lambda request: runner.provide_recovery(OomRecoveryChoice(action=STOP))
    )

    def always_oom(context: JobContext):
        raise OllamaOutOfMemoryError("out of memory")

    runner.enqueue(_job("job-1", always_oom))

    assert _drain(runner)
    assert cancelled == ["job-1"]


# Settings


def test_lab_settings_round_trip(tmp_path):
    store = LabSettingsStore(tmp_path)
    settings = LabSettings(generator_model="gen", batch_size=9, base_seed=77)

    store.save(settings)
    loaded = store.load()

    assert loaded.generator_model == "gen"
    assert loaded.batch_size == 9
    assert loaded.base_seed == 77


def test_unknown_keys_in_the_settings_file_are_ignored(tmp_path):
    store = LabSettingsStore(tmp_path)
    store.path.write_text('{"batch_size": 3, "from_the_future": true}', encoding="utf-8")

    assert store.load().batch_size == 3


def test_a_corrupt_settings_file_falls_back_to_defaults(tmp_path):
    store = LabSettingsStore(tmp_path)
    store.path.write_text("{not json", encoding="utf-8")

    assert store.load().batch_size == LabSettings().batch_size


def test_settings_are_clamped_to_valid_choices(tmp_path):
    settings = LabSettings(
        duration_minutes=9999,
        batch_size=0,
        generation_mode="sideways",
        disfluency="loud",
        generator_num_ctx=9000,
    )
    settings.validate()

    assert settings.duration_minutes == 180
    assert settings.batch_size == 1
    assert settings.generation_mode == "grounded"
    assert settings.disfluency == "light"
    assert settings.generator_num_ctx == 8192


def test_unset_model_roles_fall_back_to_the_app_model():
    settings = LabSettings(judge_model="explicit-judge")

    settings.with_model_fallback("app-model")

    assert settings.generator_model == "app-model"
    assert settings.judge_model == "explicit-judge"
