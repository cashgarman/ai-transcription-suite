from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path


LOGGER = logging.getLogger("speaker_transcriber.host")

_cpu_sample: tuple[int, int] | None = None


@dataclass(frozen=True)
class HostStats:
    cpu_percent: int | None = None
    ram_used_mb: int = 0
    ram_total_mb: int = 0

    @property
    def ram_available(self) -> bool:
        return self.ram_total_mb > 0


def query_host_stats() -> HostStats:
    used_mb, total_mb = _query_ram()
    return HostStats(
        cpu_percent=_query_cpu_percent(),
        ram_used_mb=used_mb,
        ram_total_mb=total_mb,
    )


def cpu_percent_from_samples(
    previous: tuple[int, int],
    current: tuple[int, int],
) -> int:
    idle_delta = current[0] - previous[0]
    total_delta = current[1] - previous[1]
    if total_delta <= 0:
        return 0
    busy = max(total_delta - idle_delta, 0)
    return max(0, min(round(100.0 * busy / total_delta), 100))


def parse_proc_meminfo(text: str) -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            values[parts[0].rstrip(":")] = int(parts[1])
        except ValueError:
            continue
    total_kb = values.get("MemTotal", 0)
    available_kb = values.get("MemAvailable", values.get("MemFree", 0))
    if total_kb <= 0:
        return 0, 0
    used_mb = max(total_kb - available_kb, 0) // 1024
    return used_mb, total_kb // 1024


def parse_proc_stat(text: str) -> tuple[int, int] | None:
    line = text.splitlines()[0] if text else ""
    parts = line.split()
    if not parts or parts[0] != "cpu" or len(parts) < 5:
        return None
    try:
        nums = [int(part) for part in parts[1:]]
    except ValueError:
        return None
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    return idle, sum(nums)


def _query_ram() -> tuple[int, int]:
    if sys.platform == "win32":
        return _query_ram_windows()
    return _query_ram_posix()


def _query_ram_windows() -> tuple[int, int]:
    try:
        import ctypes
    except ImportError:
        return 0, 0

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(status)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return 0, 0
    except Exception as exc:
        LOGGER.debug("GlobalMemoryStatusEx failed: %s", exc)
        return 0, 0
    total_mb = int(status.ullTotalPhys // (1024 * 1024))
    available_mb = int(status.ullAvailPhys // (1024 * 1024))
    return max(total_mb - available_mb, 0), total_mb


def _query_ram_posix() -> tuple[int, int]:
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError as exc:
        LOGGER.debug("Failed to read /proc/meminfo: %s", exc)
        return 0, 0
    return parse_proc_meminfo(text)


def _query_cpu_percent() -> int | None:
    global _cpu_sample
    times = _query_cpu_times()
    if times is None:
        return None
    previous = _cpu_sample
    _cpu_sample = times
    if previous is None:
        return None
    return cpu_percent_from_samples(previous, times)


def _query_cpu_times() -> tuple[int, int] | None:
    if sys.platform == "win32":
        return _query_cpu_times_windows()
    return _query_cpu_times_posix()


def _query_cpu_times_windows() -> tuple[int, int] | None:
    try:
        import ctypes
    except ImportError:
        return None

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", ctypes.c_uint32),
            ("dwHighDateTime", ctypes.c_uint32),
        ]

    idle = FILETIME()
    kernel = FILETIME()
    user = FILETIME()
    try:
        if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
    except Exception as exc:
        LOGGER.debug("GetSystemTimes failed: %s", exc)
        return None
    idle_time = (int(idle.dwHighDateTime) << 32) | int(idle.dwLowDateTime)
    kernel_time = (int(kernel.dwHighDateTime) << 32) | int(kernel.dwLowDateTime)
    user_time = (int(user.dwHighDateTime) << 32) | int(user.dwLowDateTime)
    return idle_time, kernel_time + user_time


def _query_cpu_times_posix() -> tuple[int, int] | None:
    try:
        text = Path("/proc/stat").read_text(encoding="utf-8")
    except OSError as exc:
        LOGGER.debug("Failed to read /proc/stat: %s", exc)
        return None
    return parse_proc_stat(text)
