from __future__ import annotations

import os
import re
import shutil
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Protocol


ADD_MODELS_SENTINEL = "__add_models__"
ALIGNMENT_AUTO = "auto"
DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
RECOMMENDED_ALIGNMENT_MODEL = "jonatasgrosman/wav2vec2-large-xlsr-53-english"
WHISPER_LARGE_V3 = "large-v3"
WHISPER_DISTIL_LARGE_V3 = "distil-large-v3"
WHISPER_MEDIUM = "medium"

WHISPER_SHORT_TO_REPO = {
    "tiny": "Systran/faster-whisper-tiny",
    "tiny.en": "Systran/faster-whisper-tiny.en",
    "base": "Systran/faster-whisper-base",
    "base.en": "Systran/faster-whisper-base.en",
    "small": "Systran/faster-whisper-small",
    "small.en": "Systran/faster-whisper-small.en",
    "medium": "Systran/faster-whisper-medium",
    "medium.en": "Systran/faster-whisper-medium.en",
    "large-v1": "Systran/faster-whisper-large-v1",
    "large-v2": "Systran/faster-whisper-large-v2",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "Systran/faster-whisper-large-v3-turbo",
    "turbo": "Systran/faster-whisper-large-v3-turbo",
    "distil-large-v2": "Systran/faster-distil-whisper-large-v2",
    "distil-large-v3": "Systran/faster-distil-whisper-large-v3",
    "distil-medium.en": "Systran/faster-distil-whisper-medium.en",
    "distil-small.en": "Systran/faster-distil-whisper-small.en",
}

WHISPER_DISPLAY_NAMES = {
    "large-v3": "whisper-large-v3 (OpenAI)",
    "distil-large-v3": "distil-large-v3",
    "medium": "medium",
}

PINNED_OLLAMA_MODELS = (
    ("llama3.2", "General / Reasoning"),
    ("qwen2.5", "Long text / high accuracy"),
)

_SIZE_RE = re.compile(
    r"(?P<value>[\d.]+)\s*(?P<unit>TB|GB|MB|KB|GIB|MIB|TIB|B)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    display_name: str = ""
    size_bytes: int | None = None
    installed: bool = False
    gated: bool = False
    description: str = ""
    family: str = ""
    role: str = ""
    is_family: bool = False

    @property
    def label(self) -> str:
        return self.display_name or self.name

    @property
    def status_label(self) -> str:
        if self.installed:
            return "Installed"
        if self.gated:
            return "Gated"
        if self.is_family:
            return "Family"
        return "Not installed"


@dataclass(frozen=True)
class DiskUsage:
    free_bytes: int
    total_bytes: int
    path: Path

    @property
    def used_bytes(self) -> int:
        return max(0, self.total_bytes - self.free_bytes)


@dataclass(frozen=True)
class DownloadProgress:
    fraction: float
    percent: int
    eta_text: str
    status: str
    completed_bytes: int = 0
    total_bytes: int = 0


class CatalogProvider(Protocol):
    id: str
    title: str

    def list_models(self, query: str = "") -> list[CatalogEntry]:
        ...

    def list_variants(self, family: str) -> list[CatalogEntry]:
        ...

    def is_installed(self, name: str) -> bool:
        ...

    def download(
        self,
        name: str,
        on_progress: Callable[[DownloadProgress], None] | None,
        cancel_event: Event,
    ) -> None:
        ...

    def cache_path(self) -> Path:
        ...


def parse_size_label(text: str) -> int | None:
    match = _SIZE_RE.search(text.replace(",", ""))
    if match is None:
        return None
    try:
        value = float(match.group("value"))
    except ValueError:
        return None
    unit = match.group("unit").upper()
    multipliers = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "TIB": 1024**4,
    }
    multiplier = multipliers.get(unit)
    if multiplier is None:
        return None
    return int(value * multiplier)


def format_bytes(size_bytes: int | None) -> str:
    if size_bytes is None or size_bytes <= 0:
        return "—"
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.1f} GB"
    if size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.0f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "—"
    total = int(round(seconds))
    if total < 1:
        return "<1s"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_disk_label(usage: DiskUsage) -> str:
    drive = usage.path.drive or str(usage.path)
    return (
        f"{format_bytes(usage.free_bytes)} free of "
        f"{format_bytes(usage.total_bytes)} on {drive}"
    )


def disk_usage_for(path: Path) -> DiskUsage:
    target = path
    while not target.exists() and target != target.parent:
        target = target.parent
    if not target.exists():
        target = Path.home()
    usage = shutil.disk_usage(target)
    return DiskUsage(free_bytes=usage.free, total_bytes=usage.total, path=path)


def huggingface_cache_dir() -> Path:
    env = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if env:
        return Path(env)
    home = os.environ.get("HF_HOME")
    if home:
        return Path(home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def ollama_models_dir() -> Path:
    env = os.environ.get("OLLAMA_MODELS")
    if env:
        return Path(env)
    user_path = Path.home() / ".ollama" / "models"
    if sys.platform.startswith("linux"):
        system_path = Path("/usr/share/ollama/.ollama/models")
        if not user_path.exists() and system_path.exists():
            return system_path
    return user_path


def _hf_cache_roots() -> list[Path]:
    roots = [huggingface_cache_dir()]
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        extra = Path(HF_HUB_CACHE)
        if extra not in roots:
            roots.append(extra)
    except Exception:
        pass
    return roots


def _hf_folder_has_files(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    for sub in ("snapshots", "blobs", "refs"):
        path = folder / sub
        if not path.is_dir():
            continue
        try:
            for child in path.iterdir():
                if child.is_file():
                    return True
                if child.is_dir():
                    try:
                        if any(child.iterdir()):
                            return True
                    except OSError:
                        continue
        except OSError:
            continue
    return False


def hf_repo_cached(repo_id: str) -> bool:
    folder_name = "models--" + repo_id.replace("/", "--")
    return any(_hf_folder_has_files(root / folder_name) for root in _hf_cache_roots())


def whisper_runtime_id(name: str) -> str:
    raw = (name or "").strip()
    lowered = raw.lower()
    aliases = {
        "openai/whisper-large-v3": "large-v3",
        "whisper-large-v3": "large-v3",
        "systran/faster-whisper-large-v3": "large-v3",
        "openai/whisper-medium": "medium",
        "systran/faster-whisper-medium": "medium",
        "systran/faster-distil-whisper-large-v3": "distil-large-v3",
    }
    if lowered in aliases:
        return aliases[lowered]
    if lowered.startswith("systran/faster-whisper-"):
        return raw.split("faster-whisper-", 1)[1]
    if lowered.startswith("systran/faster-distil-whisper-"):
        return "distil-" + raw.split("faster-distil-whisper-", 1)[1]
    return raw


def whisper_repo_id(name: str) -> str:
    runtime = whisper_runtime_id(name)
    if "/" in runtime:
        return runtime
    return WHISPER_SHORT_TO_REPO.get(runtime, f"Systran/faster-whisper-{runtime}")


def whisper_display_name(name: str) -> str:
    runtime = whisper_runtime_id(name)
    return WHISPER_DISPLAY_NAMES.get(runtime, runtime)


def _progress_field(item: object, key: str):
    value = getattr(item, key, None)
    if value is None and isinstance(item, dict):
        value = item.get(key)
    return value


def aggregate_pull_progress(
    layers: dict[str, tuple[int, int]],
    event: object,
    started_at: float,
    status_fallback: str = "Downloading",
) -> DownloadProgress:
    digest = str(_progress_field(event, "digest") or "")
    total = _progress_field(event, "total")
    completed = _progress_field(event, "completed")
    status = str(_progress_field(event, "status") or status_fallback)
    if digest and total:
        layers[digest] = (int(completed or 0), int(total))
    total_bytes = sum(item_total for _, item_total in layers.values())
    completed_bytes = sum(item_done for item_done, _ in layers.values())
    if total_bytes <= 0:
        fraction = 1.0 if "success" in status.lower() else 0.0
        return DownloadProgress(
            fraction=fraction,
            percent=int(round(fraction * 100)),
            eta_text="—" if fraction < 1 else "0s",
            status=status,
        )
    fraction = min(1.0, completed_bytes / total_bytes)
    elapsed = max(0.001, time.monotonic() - started_at)
    speed = completed_bytes / elapsed
    remaining = max(0, total_bytes - completed_bytes)
    eta = remaining / speed if speed > 0 and fraction < 1 else 0.0
    return DownloadProgress(
        fraction=fraction,
        percent=int(round(fraction * 100)),
        eta_text=format_eta(eta if fraction < 1 else 0.0),
        status=status,
        completed_bytes=completed_bytes,
        total_bytes=total_bytes,
    )


def iter_pull_events(stream: Iterator[object]) -> Iterator[object]:
    yield from stream


class ProgressTqdm:
    """Minimal tqdm stand-in that reports Hugging Face download bytes.

    Must be a real class: huggingface_hub's snapshot_download passes it to
    tqdm.contrib.concurrent.thread_map, which calls ``get_lock()`` / ``set_lock()``.
    """

    @classmethod
    def get_lock(cls):
        if getattr(cls, "_lock", None) is None:
            cls._lock = Lock()
        return cls._lock

    @classmethod
    def set_lock(cls, lock) -> None:
        cls._lock = lock

    def __init__(
        self,
        iterable=None,
        total=None,
        desc=None,
        on_progress: Callable[[DownloadProgress], None] | None = None,
        cancel_event: Event | None = None,
        started_at: float | None = None,
        **kwargs,
    ) -> None:
        self.iterable = iterable
        self.total = int(total or 0)
        self.n = int(kwargs.get("initial") or 0)
        self.desc = str(desc or kwargs.get("desc") or "Downloading")
        self.disable = bool(kwargs.get("disable", False))
        self.unit = str(kwargs.get("unit") or "")
        self.postfix = None
        self._on_progress = on_progress
        self._cancel_event = cancel_event
        self._started_at = started_at or time.monotonic()

    @property
    def format_dict(self) -> dict:
        elapsed = max(0.001, time.monotonic() - self._started_at)
        rate = self.n / elapsed if self.n else None
        return {
            "n": self.n,
            "total": self.total,
            "elapsed": elapsed,
            "rate": rate,
            "unit": self.unit,
            "prefix": self.desc,
            "postfix": self.postfix,
        }

    def _should_report(self) -> bool:
        if self._on_progress is None or self.disable:
            return False
        lowered = self.desc.lower()
        if "fetching" in lowered or "reconstruct" in lowered:
            return False
        return True

    def _emit(self) -> None:
        if not self._should_report():
            return
        total = int(self.total or 0)
        completed = int(self.n)
        if total > 0:
            fraction = min(1.0, completed / total)
        else:
            fraction = 0.0
        elapsed = max(0.001, time.monotonic() - self._started_at)
        speed = completed / elapsed
        remaining = max(0, total - completed)
        eta = remaining / speed if speed > 0 and fraction < 1 else 0.0
        self._on_progress(
            DownloadProgress(
                fraction=fraction,
                percent=int(round(fraction * 100)),
                eta_text=format_eta(eta if fraction < 1 else 0.0),
                status=self.desc,
                completed_bytes=completed,
                total_bytes=total,
            )
        )

    def update(self, n: int | float | None = 1):
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise InterruptedError("Download cancelled.")
        self.n += int(n or 0)
        self._emit()

    def refresh(self, *args, **kwargs) -> None:
        self._emit()

    def close(self) -> None:
        return None

    def set_postfix(self, *args, **kwargs) -> None:
        if args:
            self.postfix = args[0]
        elif "ordered_dict" in kwargs:
            self.postfix = kwargs["ordered_dict"]

    def set_postfix_str(self, postfix: str = "", refresh: bool = True, **kwargs) -> None:
        self.postfix = postfix
        if refresh:
            self.refresh()

    def set_description(self, desc: str | None = None, *args, **kwargs) -> None:
        if desc:
            self.desc = str(desc)

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def __iter__(self):
        for item in self.iterable or []:
            yield item
            self.update(1)


def bind_progress_tqdm(
    on_progress: Callable[[DownloadProgress], None] | None,
    cancel_event: Event | None,
    started_at: float | None = None,
) -> type[ProgressTqdm]:
    """Return a tqdm-compatible class that reports into ``on_progress``."""

    started = started_at or time.monotonic()

    class BoundProgressTqdm(ProgressTqdm):
        def __init__(self, iterable=None, total=None, desc=None, **kwargs) -> None:
            super().__init__(
                iterable,
                total=total,
                desc=desc,
                on_progress=on_progress,
                cancel_event=cancel_event,
                started_at=started,
                **kwargs,
            )

    BoundProgressTqdm.__name__ = "BoundProgressTqdm"
    return BoundProgressTqdm
