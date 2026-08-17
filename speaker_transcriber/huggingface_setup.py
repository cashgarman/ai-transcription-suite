from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from speaker_transcriber.huggingface_compat import patch_hf_hub_use_auth_token


LOGGER = logging.getLogger("speaker_transcriber.huggingface")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CONFIGURED = False

DEFAULT_DIARIZATION_PIPELINE = "pyannote/speaker-diarization-3.1"
KNOWN_PYANNOTE_PIPELINES = {
    DEFAULT_DIARIZATION_PIPELINE,
    "pyannote/speaker-diarization-3.0",
}

DIARIZATION_MODEL_ASSETS: tuple[tuple[str, str], ...] = (
    (DEFAULT_DIARIZATION_PIPELINE, "config.yaml"),
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
    """Load .env and install a Hub HTTP client with retries (and optional insecure SSL)."""
    global _CONFIGURED
    load_project_env()

    from huggingface_hub.utils._http import (
        async_hf_request_event_hook,
        async_hf_response_event_hook,
        hf_request_event_hook,
        set_async_client_factory,
        set_client_factory,
    )

    verify = not _insecure_ssl_enabled()

    def client_factory() -> httpx.Client:
        return httpx.Client(
            event_hooks={"request": [hf_request_event_hook]},
            follow_redirects=True,
            timeout=None,
            verify=verify,
            transport=httpx.HTTPTransport(retries=5, verify=verify),
        )

    def async_client_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            event_hooks={
                "request": [async_hf_request_event_hook],
                "response": [async_hf_response_event_hook],
            },
            follow_redirects=True,
            timeout=None,
            verify=verify,
            transport=httpx.AsyncHTTPTransport(retries=5, verify=verify),
        )

    set_client_factory(client_factory)
    set_async_client_factory(async_client_factory)
    _CONFIGURED = True
    if not verify:
        LOGGER.warning(
            "HF_HUB_INSECURE_SSL is enabled. Hugging Face downloads will skip SSL "
            "certificate verification. Disable this after models are cached if possible."
        )


def _http_status(exc: BaseException) -> int | None:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status = getattr(current, "status_code", None)
        if status:
            try:
                return int(status)
            except (TypeError, ValueError):
                pass
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None)
        if status:
            try:
                return int(status)
            except (TypeError, ValueError):
                pass
        current = current.__cause__ or current.__context__
    return None


def is_retryable_download_error(exc: BaseException) -> bool:
    status = _http_status(exc)
    if status is not None:
        return status == 429 or status >= 500
    name = type(exc).__name__.lower()
    if any(
        marker in name
        for marker in ("entrynotfound", "repositorynotfound", "gatedrepo", "badrequest")
    ):
        return False
    network_terms = (
        "10054",
        "connection",
        "forcibly closed",
        "certificate",
        "ssl",
        "remote host",
        "timeout",
        "reset",
        "temporarily unavailable",
        "localentrynotfound",
    )
    if isinstance(
        exc,
        (ConnectionError, TimeoutError, httpx.ConnectError, httpx.TimeoutException),
    ):
        return True
    message = str(exc).lower()
    if isinstance(exc, OSError):
        return any(term in message for term in network_terms)
    return any(term in message for term in network_terms)


def unsupported_diarization_model_message(repo_id: str) -> str:
    name = (repo_id or DEFAULT_DIARIZATION_PIPELINE).strip() or DEFAULT_DIARIZATION_PIPELINE
    return (
        f"{name} is not a pyannote speaker-diarization pipeline. "
        "This app loads pyannote pipelines, which include a config.yaml file. "
        "CoreML, ONNX, and similar conversions cannot be used. "
        f"Select {DEFAULT_DIARIZATION_PIPELINE} instead."
    )


def require_pyannote_pipeline(repo_id: str, token: str | None = None) -> None:
    pipeline_id = (repo_id or "").strip()
    if not pipeline_id or pipeline_id in KNOWN_PYANNOTE_PIPELINES:
        return
    from huggingface_hub import list_repo_files

    files = list_repo_files(pipeline_id, token=token)
    if "config.yaml" not in files:
        raise RuntimeError(unsupported_diarization_model_message(pipeline_id))


def retry_hub_operation(
    operation,
    *,
    max_attempts: int = 5,
    cancel_event=None,
    what: str = "Hugging Face request",
):
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Download cancelled.")
        try:
            return operation()
        except InterruptedError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt == max_attempts or not is_retryable_download_error(exc):
                raise
            delay_seconds = min(2**attempt, 30)
            LOGGER.warning(
                "Retrying %s in %d seconds (attempt %d/%d: %s)",
                what,
                delay_seconds,
                attempt,
                max_attempts,
                exc,
            )
            time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{what} failed without an error.")


def prefetch_diarization_models(
    token: str,
    model_id: str | None = None,
    max_attempts: int = 5,
) -> None:
    """Download pyannote assets up front so diarization can run offline later."""
    configure_huggingface_client()
    patch_hf_hub_use_auth_token()
    from huggingface_hub import hf_hub_download, snapshot_download

    pipeline_id = (model_id or DEFAULT_DIARIZATION_PIPELINE).strip() or (
        DEFAULT_DIARIZATION_PIPELINE
    )
    custom_pipeline = pipeline_id != DEFAULT_DIARIZATION_PIPELINE
    if custom_pipeline:
        require_pyannote_pipeline(pipeline_id, token)
        assets: tuple[tuple[str, str], ...] = ()
    else:
        assets = DIARIZATION_MODEL_ASSETS
    if custom_pipeline:
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                snapshot_download(pipeline_id, token=token)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt == max_attempts or not is_retryable_download_error(exc):
                    raise
                time.sleep(min(2**attempt, 30))
        if last_error is not None:
            raise last_error
    for repo_id, filename in assets:
        for attempt in range(1, max_attempts + 1):
            try:
                hf_hub_download(repo_id, filename, token=token)
                break
            except Exception as exc:
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
