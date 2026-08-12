from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from speaker_transcriber.debug_log import agent_log
from speaker_transcriber.huggingface_compat import patch_hf_hub_use_auth_token


LOGGER = logging.getLogger("speaker_transcriber.huggingface")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CONFIGURED = False

DIARIZATION_MODEL_ASSETS: tuple[tuple[str, str], ...] = (
    ("pyannote/speaker-diarization-3.1", "config.yaml"),
    ("pyannote/segmentation-3.0", "config.yaml"),
    ("pyannote/segmentation-3.0", "pytorch_model.bin"),
    ("pyannote/wespeaker-voxceleb-resnet34-LM", "config.yaml"),
    ("pyannote/wespeaker-voxceleb-resnet34-LM", "pytorch_model.bin"),
)


def _is_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def load_project_env() -> None:
    load_dotenv()
    load_dotenv(PROJECT_ROOT / ".env")


def _insecure_ssl_enabled() -> bool:
    return _is_enabled(os.environ.get("HF_HUB_INSECURE_SSL"))


def configure_huggingface_client() -> None:
    """Load .env and optionally relax SSL verification for Hub downloads."""
    global _CONFIGURED
    load_project_env()

    if not _insecure_ssl_enabled():
        _CONFIGURED = True
        return

    from huggingface_hub.utils._http import (
        set_async_client_factory,
        set_client_factory,
    )

    def client_factory() -> httpx.Client:
        return httpx.Client(
            follow_redirects=True,
            timeout=None,
            verify=False,
        )

    def async_client_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            follow_redirects=True,
            timeout=None,
            verify=False,
        )

    set_client_factory(client_factory)
    set_async_client_factory(async_client_factory)
    _CONFIGURED = True
    LOGGER.warning(
        "HF_HUB_INSECURE_SSL is enabled. Hugging Face downloads will skip SSL "
        "certificate verification. Disable this after models are cached if possible."
    )


def is_retryable_download_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    message = str(exc).lower()
    return any(
        term in message
        for term in (
            "10054",
            "connection",
            "forcibly closed",
            "certificate",
            "ssl",
            "remote host",
            "timeout",
            "reset",
            "temporarily unavailable",
        )
    )


def prefetch_diarization_models(token: str, max_attempts: int = 5) -> None:
    """Download pyannote assets up front so diarization can run offline later."""
    configure_huggingface_client()
    patch_hf_hub_use_auth_token()
    from huggingface_hub import hf_hub_download

    agent_log(
        "huggingface_setup.py:prefetch_diarization_models",
        "prefetch started",
        {
            "asset_count": len(DIARIZATION_MODEL_ASSETS),
            "insecure_ssl": _insecure_ssl_enabled(),
        },
        "H6",
    )
    for repo_id, filename in DIARIZATION_MODEL_ASSETS:
        for attempt in range(1, max_attempts + 1):
            try:
                hf_hub_download(repo_id, filename, token=token)
                agent_log(
                    "huggingface_setup.py:prefetch_diarization_models",
                    "prefetch asset cached",
                    {"repo_id": repo_id, "filename": filename, "attempt": attempt},
                    "H6",
                )
                break
            except Exception as exc:
                agent_log(
                    "huggingface_setup.py:prefetch_diarization_models",
                    "prefetch asset failed",
                    {
                        "repo_id": repo_id,
                        "filename": filename,
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    },
                    "H6",
                )
                if attempt == max_attempts or not is_retryable_download_error(exc):
                    raise
                delay_seconds = min(2**attempt, 30)
                LOGGER.warning(
                    "Retrying Hugging Face download for %s/%s in %d seconds (%s)",
                    repo_id,
                    filename,
                    delay_seconds,
                    exc,
                )
                time.sleep(delay_seconds)
    agent_log(
        "huggingface_setup.py:prefetch_diarization_models",
        "prefetch complete",
        {"asset_count": len(DIARIZATION_MODEL_ASSETS)},
        "H6",
    )
