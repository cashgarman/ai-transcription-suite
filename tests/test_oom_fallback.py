from speaker_transcriber.models.model_manager import ModelManager
from speaker_transcriber.pipeline.types import ProcessingOptions


def test_oom_reduces_batch_then_model(monkeypatch) -> None:
    manager = ModelManager()
    monkeypatch.setattr(manager, "clear_cuda", lambda: None)
    attempts = []

    def operation(options):
        attempts.append((options.model, options.batch_size))
        if len(attempts) < 4:
            raise RuntimeError("CUDA out of memory")
        return "ok"

    decisions = []
    result, chosen = manager.run_transcription_with_fallback(
        operation,
        ProcessingOptions(model="large-v3", batch_size=4),
        decisions,
    )
    assert result == "ok"
    assert attempts == [
        ("large-v3", 4),
        ("large-v3", 2),
        ("large-v3", 1),
        ("distil-large-v3", 4),
    ]
    assert chosen.model == "distil-large-v3"
    assert len(decisions) == 3


def test_device_stage_moves_to_cpu(monkeypatch) -> None:
    manager = ModelManager()
    monkeypatch.setattr(manager, "clear_cuda", lambda: None)
    calls = []

    def operation(device):
        calls.append(device)
        if device == "cuda":
            raise RuntimeError("CUDA out of memory")
        return "done"

    result, device = manager.run_device_stage_with_fallback(
        operation,
        "cuda",
        "alignment",
        [],
    )
    assert result == "done"
    assert device == "cpu"
    assert calls == ["cuda", "cpu"]
