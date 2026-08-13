from __future__ import annotations

import gc
import logging
from dataclasses import replace
from typing import Callable, TypeVar

from speaker_transcriber.pipeline.types import ProcessingOptions


LOGGER = logging.getLogger("speaker_transcriber.models")
T = TypeVar("T")


def is_cuda_oom(error: BaseException) -> bool:
    return error.__class__.__name__ == "OutOfMemoryError" or (
        isinstance(error, RuntimeError)
        and "out of memory" in str(error).lower()
        and "cuda" in str(error).lower()
    )


class ModelManager:
    def get_vram_info(self) -> tuple[int, int]:
        import torch

        if not torch.cuda.is_available():
            return 0, 0
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        used_bytes = total_bytes - free_bytes
        return int(used_bytes / 1024**2), int(total_bytes / 1024**2)

    def clear_cuda(self) -> None:
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def release(self, model: object | None) -> None:
        if model is not None:
            del model
        self.clear_cuda()

    def run_transcription_with_fallback(
        self,
        operation: Callable[[ProcessingOptions], T],
        options: ProcessingOptions,
        decisions: list[str],
    ) -> tuple[T, ProcessingOptions]:
        current = replace(options)
        attempted: set[tuple[str, int]] = set()
        while True:
            configuration = (current.model, current.batch_size)
            if configuration in attempted:
                raise RuntimeError("CUDA fallback options were exhausted.")
            attempted.add(configuration)
            try:
                return operation(current), current
            except BaseException as exc:
                if not is_cuda_oom(exc):
                    raise
                self.clear_cuda()
                if current.batch_size > 1:
                    reduced = max(1, current.batch_size // 2)
                    decisions.append(f"CUDA OOM: batch size reduced to {reduced}.")
                    LOGGER.warning(decisions[-1])
                    current = replace(current, batch_size=reduced)
                    continue
                if current.model == "large-v3":
                    decisions.append("CUDA OOM: model changed from large-v3 to distil-large-v3.")
                    LOGGER.warning(decisions[-1])
                    current = replace(current, model="distil-large-v3", batch_size=options.batch_size)
                    continue
                if current.model == "distil-large-v3":
                    decisions.append("CUDA OOM: model changed from distil-large-v3 to medium.")
                    LOGGER.warning(decisions[-1])
                    current = replace(current, model="medium", batch_size=options.batch_size)
                    continue
                raise RuntimeError(
                    "The GPU ran out of memory even with the medium model and batch size 1. "
                    "Close other GPU applications or select CPU processing."
                ) from exc

    def run_device_stage_with_fallback(
        self,
        operation: Callable[[str], T],
        requested_device: str,
        stage_name: str,
        decisions: list[str],
    ) -> tuple[T, str]:
        try:
            return operation(requested_device), requested_device
        except BaseException as exc:
            if requested_device != "cuda" or not is_cuda_oom(exc):
                raise
            self.clear_cuda()
            decision = f"CUDA OOM: {stage_name} moved to CPU."
            decisions.append(decision)
            LOGGER.warning(decision)
            return operation("cpu"), "cpu"
