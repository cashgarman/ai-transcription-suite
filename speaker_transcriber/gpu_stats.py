from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass


LOGGER = logging.getLogger("speaker_transcriber.gpu")


@dataclass(frozen=True)
class GpuStats:
    vram_used_mb: int = 0
    vram_total_mb: int = 0
    gpu_util_percent: int = 0

    @property
    def available(self) -> bool:
        return self.vram_total_mb > 0


def query_gpu_stats() -> GpuStats:
    stats = _query_nvidia_smi()
    if stats.available:
        return stats
    return _query_torch_vram()


def _query_nvidia_smi() -> GpuStats:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return GpuStats()
    try:
        completed = subprocess.run(
            [
                executable,
                "--query-gpu=memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        LOGGER.debug("nvidia-smi query failed: %s", exc)
        return GpuStats()
    if completed.returncode != 0 or not completed.stdout.strip():
        return GpuStats()
    line = completed.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 3:
        return GpuStats()
    try:
        used = int(float(parts[0]))
        total = int(float(parts[1]))
        util = int(float(parts[2]))
    except ValueError:
        return GpuStats()
    return GpuStats(
        vram_used_mb=max(used, 0),
        vram_total_mb=max(total, 0),
        gpu_util_percent=max(0, min(util, 100)),
    )


def _query_torch_vram() -> GpuStats:
    try:
        import torch
    except ImportError:
        return GpuStats()
    if not torch.cuda.is_available():
        return GpuStats()
    try:
        free_bytes, total_bytes = torch.cuda.mem_get_info()
    except Exception as exc:
        LOGGER.debug("torch VRAM query failed: %s", exc)
        return GpuStats()
    used_mb = int((total_bytes - free_bytes) / 1024**2)
    total_mb = int(total_bytes / 1024**2)
    return GpuStats(vram_used_mb=used_mb, vram_total_mb=total_mb, gpu_util_percent=0)
