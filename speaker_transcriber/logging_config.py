from __future__ import annotations

import logging
import json
import os
import platform
import re
import sys
from logging.handlers import QueueHandler, RotatingFileHandler
from pathlib import Path
from queue import Queue

from speaker_transcriber import __version__
from speaker_transcriber.config import app_data_dir


LOGGER_NAME = "speaker_transcriber"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class SecretRedactionFilter(logging.Filter):
    _patterns = (
        re.compile(r"(HF_TOKEN\s*[=:]\s*)\S+", re.IGNORECASE),
        re.compile(r"(--hf-token(?:=|\s+))\S+", re.IGNORECASE),
        re.compile(r"(Bearer\s+)[A-Za-z0-9_.-]+", re.IGNORECASE),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self._patterns:
            message = pattern.sub(r"\1[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging(
    verbose: bool = False,
    gui_queue: Queue[logging.LogRecord] | None = None,
    log_directory: Path | None = None,
) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        "%Y-%m-%dT%H:%M:%S",
    )
    redactor = SecretRedactionFilter()

    directory = log_directory or app_data_dir() / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        directory / "speaker_transcriber.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(redactor)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(redactor)
    logger.addHandler(stream_handler)

    if gui_queue is not None:
        queue_handler = QueueHandler(gui_queue)
        queue_handler.setFormatter(formatter)
        queue_handler.addFilter(redactor)
        logger.addHandler(queue_handler)

    return logger


def log_system_information(logger: logging.Logger) -> None:
    try:
        import torch
    except ImportError:
        logger.warning("PyTorch is not installed; model processing is unavailable.")
        return

    logger.info("Speaker Transcriber %s", __version__)
    logger.info("Python %s on %s", sys.version.split()[0], platform.platform())
    logger.info(
        "PyTorch %s; CUDA available=%s; CUDA runtime=%s",
        torch.__version__,
        torch.cuda.is_available(),
        torch.version.cuda or "none",
    )
    if torch.cuda.is_available():
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        logger.info(
            "GPU %s; VRAM free %.2f GB / %.2f GB",
            torch.cuda.get_device_name(0),
            free_bytes / 1024**3,
            total_bytes / 1024**3,
        )
    logger.debug("Process ID %d", os.getpid())
