from speaker_transcriber.gpu_stats import GpuStats, _query_nvidia_smi


def test_gpu_stats_dataclass_defaults() -> None:
    stats = GpuStats()
    assert stats.available is False
    assert stats.gpu_util_percent == 0


def test_nvidia_smi_parse_via_monkeypatch(monkeypatch) -> None:
    class FakeCompleted:
        returncode = 0
        stdout = "2048, 8192, 37\n"

    monkeypatch.setattr(
        "speaker_transcriber.gpu_stats.shutil.which",
        lambda _name: "nvidia-smi",
    )
    monkeypatch.setattr(
        "speaker_transcriber.gpu_stats.subprocess.run",
        lambda *_args, **_kwargs: FakeCompleted(),
    )
    stats = _query_nvidia_smi()
    assert stats.vram_used_mb == 2048
    assert stats.vram_total_mb == 8192
    assert stats.gpu_util_percent == 37
    assert stats.available is True
