from speaker_transcriber.host_stats import (
    HostStats,
    cpu_percent_from_samples,
    parse_proc_meminfo,
    parse_proc_stat,
)


def test_host_stats_defaults() -> None:
    stats = HostStats()
    assert stats.ram_available is False
    assert stats.cpu_percent is None


def test_cpu_percent_from_samples() -> None:
    previous = (100, 400)
    current = (150, 600)
    assert cpu_percent_from_samples(previous, current) == 75


def test_cpu_percent_clamps_and_handles_no_delta() -> None:
    assert cpu_percent_from_samples((10, 10), (10, 10)) == 0
    assert cpu_percent_from_samples((0, 100), (0, 200)) == 100


def test_parse_proc_meminfo() -> None:
    text = (
        "MemTotal:       16384000 kB\n"
        "MemFree:         2048000 kB\n"
        "MemAvailable:    4096000 kB\n"
    )
    used_mb, total_mb = parse_proc_meminfo(text)
    assert total_mb == 16000
    assert used_mb == 12000


def test_parse_proc_stat() -> None:
    times = parse_proc_stat("cpu  10 20 30 40 10 0 0 0\ncpu0 1 2 3 4 5\n")
    assert times == (50, 110)
