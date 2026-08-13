from __future__ import annotations

import logging
from collections.abc import Callable
from threading import Event

from speaker_transcriber.models.model_catalog import (
    ALIGNMENT_AUTO,
    CatalogEntry,
    DEFAULT_DIARIZATION_MODEL,
    DownloadProgress,
    bind_progress_tqdm,
    RECOMMENDED_ALIGNMENT_MODEL,
    WHISPER_DISTIL_LARGE_V3,
    WHISPER_LARGE_V3,
    WHISPER_MEDIUM,
    disk_usage_for,
    hf_repo_cached,
    huggingface_cache_dir,
    whisper_display_name,
    whisper_repo_id,
    whisper_runtime_id,
)


LOGGER = logging.getLogger("speaker_transcriber.hf_catalog")

RECOMMENDED_WHISPER = (
    (WHISPER_LARGE_V3, "OpenAI Whisper large-v3"),
    (WHISPER_DISTIL_LARGE_V3, "Faster distilled large-v3"),
    (WHISPER_MEDIUM, "Balanced speed and accuracy"),
)

RECOMMENDED_DIARIZATION = (
    (DEFAULT_DIARIZATION_MODEL, "Recommended pyannote 3.1 pipeline"),
    ("pyannote/speaker-diarization-3.0", "Previous pyannote 3.0 pipeline"),
)

_INCOMPATIBLE_DIARIZATION_MARKERS = (
    "coreml",
    "-onnx",
    "/onnx",
    "openvino",
    "tflite",
    "tensorrt",
    "mlmodel",
)


_LIST_EXPAND = ["usedStorage", "siblings", "gated"]


def _sibling_size(info: object) -> int | None:
    siblings = getattr(info, "siblings", None) or []
    total = 0
    found = False
    for sibling in siblings:
        size = getattr(sibling, "size", None)
        if size is None and isinstance(sibling, dict):
            size = sibling.get("size")
        if size:
            total += int(size)
            found = True
    return total if found else None


def _repo_size(info: object | None) -> int | None:
    if info is None:
        return None
    used = getattr(info, "used_storage", None)
    if used:
        try:
            value = int(used)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return _sibling_size(info)


def _catalog_size(model: object, token: str | None, repo_id: str = "") -> int | None:
    size = _repo_size(model)
    if size:
        return size
    name = repo_id or str(getattr(model, "id", "") or "")
    if not name:
        return None
    return _repo_size(_model_info(name, token))


def _is_gated(info: object) -> bool:
    gated = getattr(info, "gated", False)
    if gated in (False, None, "", "false"):
        return False
    return True


def _sibling_filenames(info: object | None) -> set[str]:
    if info is None:
        return set()
    siblings = getattr(info, "siblings", None) or []
    names: set[str] = set()
    for sibling in siblings:
        name = getattr(sibling, "rfilename", None)
        if name is None and isinstance(sibling, dict):
            name = sibling.get("rfilename")
        if name:
            names.add(str(name))
    return names


def _is_pyannote_pipeline_candidate(repo_id: str, info: object | None = None) -> bool:
    lowered = repo_id.lower()
    if any(marker in lowered for marker in _INCOMPATIBLE_DIARIZATION_MARKERS):
        return False
    filenames = _sibling_filenames(info)
    if filenames and "config.yaml" not in filenames:
        return False
    return "diarization" in lowered or "pyannote" in lowered


def _hf_api(token: str | None = None):
    from huggingface_hub import HfApi

    from speaker_transcriber.huggingface_setup import configure_huggingface_client

    configure_huggingface_client()
    return HfApi(token=token) if token else HfApi()


def _list_hub_models(token: str | None = None, **kwargs) -> list:
    api = _hf_api(token)
    try:
        return list(api.list_models(expand=_LIST_EXPAND, **kwargs))
    except TypeError:
        LOGGER.debug("Hub listing does not support expand; retrying without it")
    except Exception:
        LOGGER.debug("Hub listing with expand failed; retrying without it", exc_info=True)
    try:
        return list(api.list_models(**kwargs))
    except Exception:
        LOGGER.debug("Hub listing failed", exc_info=True)
        return []


def _model_info(repo_id: str, token: str | None = None) -> object | None:
    try:
        return _hf_api(token).model_info(repo_id, files_metadata=True)
    except Exception:
        LOGGER.debug("model_info failed for %s", repo_id, exc_info=True)
        try:
            return _hf_api(token).model_info(repo_id)
        except Exception:
            LOGGER.debug("model_info retry failed for %s", repo_id, exc_info=True)
            return None


def _entry_from_repo(
    repo_id: str,
    *,
    display_name: str = "",
    description: str = "",
    token: str | None = None,
    installed: bool | None = None,
) -> CatalogEntry:
    info = _model_info(repo_id, token)
    size = _repo_size(info)
    gated = _is_gated(info) if info is not None else False
    if installed is None:
        installed = hf_repo_cached(repo_id)
    return CatalogEntry(
        name=repo_id,
        display_name=display_name or repo_id,
        size_bytes=size,
        installed=installed,
        gated=gated,
        description=description or str(getattr(info, "pipeline_tag", "") or ""),
        family=repo_id.split("/")[0] if "/" in repo_id else repo_id,
    )


def _snapshot_download(
    repo_id: str,
    token: str | None,
    on_progress: Callable[[DownloadProgress], None] | None,
    cancel_event: Event,
) -> None:
    from huggingface_hub import snapshot_download

    from speaker_transcriber.huggingface_setup import (
        configure_huggingface_client,
        is_retryable_download_error,
        retry_hub_operation,
    )

    configure_huggingface_client()
    tqdm_class = bind_progress_tqdm(on_progress, cancel_event)
    try:
        retry_hub_operation(
            lambda: snapshot_download(
                repo_id=repo_id,
                token=token,
                tqdm_class=tqdm_class,
            ),
            cancel_event=cancel_event,
            what=f"download {repo_id}",
        )
    except InterruptedError:
        raise
    except Exception as exc:
        if is_retryable_download_error(exc):
            raise RuntimeError(
                f"Could not download {repo_id} from Hugging Face. "
                "The connection was reset while contacting the Hub. "
                "Set HF_HUB_INSECURE_SSL=1 in .env, retry the download, then "
                "remove it after the model is cached."
            ) from exc
        raise


class WhisperCatalogProvider:
    id = "whisper"
    title = "Transcribe audio"

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def list_models(self, query: str = "") -> list[CatalogEntry]:
        needle = query.strip().lower()
        entries: list[CatalogEntry] = []
        seen: set[str] = set()
        for short_name, role in RECOMMENDED_WHISPER:
            runtime = whisper_runtime_id(short_name)
            repo = whisper_repo_id(runtime)
            entry = CatalogEntry(
                name=runtime,
                display_name=whisper_display_name(runtime),
                size_bytes=_repo_size(_model_info(repo, self.token)),
                installed=hf_repo_cached(repo),
                description=role,
                family="whisper",
                role=role,
            )
            if needle and needle not in runtime.lower() and needle not in entry.display_name.lower():
                continue
            entries.append(entry)
            seen.add(runtime)
            seen.add(repo.lower())
        models = _list_hub_models(
            self.token,
            author="Systran",
            search="faster-whisper",
            limit=40,
        )
        for model in models:
            repo_id = str(getattr(model, "id", "") or "")
            if not repo_id or repo_id.lower() in seen:
                continue
            runtime = whisper_runtime_id(repo_id)
            if needle and needle not in runtime.lower() and needle not in repo_id.lower():
                continue
            entries.append(
                CatalogEntry(
                    name=runtime,
                    display_name=whisper_display_name(runtime),
                    size_bytes=_catalog_size(model, self.token, repo_id),
                    installed=hf_repo_cached(repo_id),
                    gated=_is_gated(model),
                    description=str(getattr(model, "pipeline_tag", "") or ""),
                    family="whisper",
                )
            )
            seen.add(runtime)
            seen.add(repo_id.lower())
        if needle and not entries:
            repo = needle if "/" in query else whisper_repo_id(query)
            entries.append(_entry_from_repo(repo, display_name=query, token=self.token))
        return entries

    def list_variants(self, family: str) -> list[CatalogEntry]:
        return []

    def is_installed(self, name: str) -> bool:
        return hf_repo_cached(whisper_repo_id(name))

    def download(
        self,
        name: str,
        on_progress: Callable[[DownloadProgress], None] | None,
        cancel_event: Event,
    ) -> None:
        _snapshot_download(whisper_repo_id(name), self.token, on_progress, cancel_event)

    def cache_path(self):
        return huggingface_cache_dir()

    def disk_usage(self):
        return disk_usage_for(self.cache_path())


class AlignmentCatalogProvider:
    id = "alignment"
    title = "Align word timestamps"

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def list_models(self, query: str = "") -> list[CatalogEntry]:
        needle = query.strip().lower()
        recommended = _entry_from_repo(
            RECOMMENDED_ALIGNMENT_MODEL,
            display_name="wav2vec2-large-xlsr-53-english",
            description="Recommended English aligner",
            token=self.token,
        )
        entries = [
            CatalogEntry(
                name=recommended.name,
                display_name=recommended.display_name,
                size_bytes=recommended.size_bytes,
                installed=recommended.installed,
                gated=recommended.gated,
                description="Recommended English aligner",
                family="alignment",
                role="English wav2vec2",
            )
        ]
        models = _list_hub_models(
            self.token,
            search=query.strip() or "wav2vec2 xlsr asr",
            limit=30,
        )
        seen = {RECOMMENDED_ALIGNMENT_MODEL}
        for model in models:
            repo_id = str(getattr(model, "id", "") or "")
            if not repo_id or repo_id in seen:
                continue
            if "wav2vec2" not in repo_id.lower():
                continue
            if needle and needle not in repo_id.lower():
                continue
            entries.append(
                CatalogEntry(
                    name=repo_id,
                    display_name=repo_id,
                    size_bytes=_catalog_size(model, self.token, repo_id),
                    installed=hf_repo_cached(repo_id),
                    gated=_is_gated(model),
                    family="alignment",
                )
            )
            seen.add(repo_id)
        if needle:
            entries = [
                entry
                for entry in entries
                if needle in entry.name.lower() or needle in entry.display_name.lower()
            ]
        return entries

    def list_variants(self, family: str) -> list[CatalogEntry]:
        return []

    def is_installed(self, name: str) -> bool:
        if name in ("", ALIGNMENT_AUTO):
            return True
        return hf_repo_cached(name)

    def download(
        self,
        name: str,
        on_progress: Callable[[DownloadProgress], None] | None,
        cancel_event: Event,
    ) -> None:
        if name in ("", ALIGNMENT_AUTO):
            return
        _snapshot_download(name, self.token, on_progress, cancel_event)

    def cache_path(self):
        return huggingface_cache_dir()

    def disk_usage(self):
        return disk_usage_for(self.cache_path())


class DiarizationCatalogProvider:
    id = "diarization"
    title = "Detect speakers"

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def list_models(self, query: str = "") -> list[CatalogEntry]:
        needle = query.strip().lower()
        entries: list[CatalogEntry] = []
        seen: set[str] = set()
        for repo_id, role in RECOMMENDED_DIARIZATION:
            entry = _entry_from_repo(
                repo_id,
                display_name=repo_id,
                description=role,
                token=self.token,
            )
            entry = CatalogEntry(
                name=entry.name,
                display_name=entry.display_name,
                size_bytes=entry.size_bytes,
                installed=entry.installed,
                gated=True,
                description=role,
                family="pyannote",
                role=role,
            )
            if needle and needle not in repo_id.lower():
                continue
            entries.append(entry)
            seen.add(repo_id)
        models = _list_hub_models(
            self.token,
            search=query.strip() or "speaker-diarization",
            limit=30,
        )
        for model in models:
            repo_id = str(getattr(model, "id", "") or "")
            if not repo_id or repo_id in seen:
                continue
            lowered = repo_id.lower()
            if not _is_pyannote_pipeline_candidate(repo_id, model):
                continue
            if needle and needle not in lowered:
                continue
            entries.append(
                CatalogEntry(
                    name=repo_id,
                    display_name=repo_id,
                    size_bytes=_catalog_size(model, self.token, repo_id),
                    installed=hf_repo_cached(repo_id),
                    gated=_is_gated(model) or lowered.startswith("pyannote/"),
                    family="pyannote",
                )
            )
            seen.add(repo_id)
        return entries

    def list_variants(self, family: str) -> list[CatalogEntry]:
        return []

    def is_installed(self, name: str) -> bool:
        return hf_repo_cached(name)

    def download(
        self,
        name: str,
        on_progress: Callable[[DownloadProgress], None] | None,
        cancel_event: Event,
    ) -> None:
        _snapshot_download(name, self.token, on_progress, cancel_event)

    def cache_path(self):
        return huggingface_cache_dir()

    def disk_usage(self):
        return disk_usage_for(self.cache_path())
