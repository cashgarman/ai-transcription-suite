from __future__ import annotations

import json
import logging
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event
from urllib.parse import quote, urlencode

from speaker_transcriber.models.model_catalog import (
    CatalogEntry,
    DownloadProgress,
    PINNED_OLLAMA_MODELS,
    aggregate_pull_progress,
    disk_usage_for,
    ollama_models_dir,
    parse_size_label,
)
from speaker_transcriber.models.summarization import RequirementsSummarizer


LOGGER = logging.getLogger("speaker_transcriber.ollama_catalog")
_LIBRARY_HREF = re.compile(r'href="/(?:library/)?([a-zA-Z0-9._-]+)"')
_HEADING_NAME = re.compile(r"<h2[^>]*>\s*([^<]+?)\s*</h2>", re.IGNORECASE)
_TAG_ROW = re.compile(
    r"(?P<name>[a-zA-Z0-9._/-]+:[a-zA-Z0-9._-]+)"
    r".{0,160}?"
    r"(?P<size>[\d.]+)\s*(?P<unit>GB|MB|TB|GiB|MiB)\b",
    re.IGNORECASE,
)
_USER_AGENT = "Summit-Transcriber/1.0"
_PINNED_DEFAULT_SIZES = {
    "llama3.2": 2_000_000_000,
    "qwen2.5": 4_700_000_000,
}


def http_get(url: str, timeout: float = 30.0, accept: str = "text/html") -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": accept,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_ollama_search_html(html: str) -> list[CatalogEntry]:
    names: list[str] = []
    seen: set[str] = set()
    for match in _LIBRARY_HREF.finditer(html):
        name = match.group(1).strip()
        if name in {"library", "search", "blog", "docs", "download", "signin"}:
            continue
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    if not names:
        for match in _HEADING_NAME.finditer(html):
            name = match.group(1).strip().lower().replace(" ", "-")
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return [
        CatalogEntry(name=name, display_name=name, family=name, is_family=True)
        for name in names
    ]


def parse_ollama_search_json(payload: object) -> list[CatalogEntry] | None:
    if isinstance(payload, dict):
        models = payload.get("models") or payload.get("items") or payload.get("pages")
    elif isinstance(payload, list):
        models = payload
    else:
        return None
    if not isinstance(models, list) or not models:
        return None
    entries: list[CatalogEntry] = []
    for item in models:
        if isinstance(item, str):
            name = item
            description = ""
            size_bytes = None
        elif isinstance(item, dict):
            name = str(
                item.get("name")
                or item.get("model")
                or item.get("model_id")
                or item.get("id")
                or ""
            ).strip()
            if "/" in name and name.startswith("library/"):
                name = name.split("/", 1)[1]
            description = str(item.get("description") or "")
            size_bytes = _json_size(item)
        else:
            continue
        if not name:
            continue
        entries.append(
            CatalogEntry(
                name=name,
                display_name=name,
                size_bytes=size_bytes,
                description=description,
                family=name.split(":", 1)[0],
                is_family=":" not in name,
            )
        )
    return entries or None


def parse_ollama_tags_html(html: str, family: str) -> list[CatalogEntry]:
    entries: dict[str, CatalogEntry] = {}
    for match in _TAG_ROW.finditer(html):
        name = match.group("name")
        size = parse_size_label(f"{match.group('size')} {match.group('unit')}")
        if name.startswith(family) or ":" in name:
            entries[name] = CatalogEntry(
                name=name,
                display_name=name,
                size_bytes=size,
                family=family,
            )
    return list(entries.values())


def parse_ollama_library_size(html: str, family: str) -> int | None:
    pattern = re.compile(
        rf"{re.escape(family)}:latest.{{0,600}}?(?P<size>[\d.]+)\s*(?P<unit>GB|MB|TB|GiB|MiB)\b",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(html)
    if match is None:
        match = re.search(
            rf"{re.escape(family)}:[a-zA-Z0-9._-]+.{{0,400}}?(?P<size>[\d.]+)\s*(?P<unit>GB|MB|TB|GiB|MiB)\b",
            html,
            re.IGNORECASE | re.DOTALL,
        )
    if match is None:
        return None
    return parse_size_label(f"{match.group('size')} {match.group('unit')}")


def _json_size(item: dict) -> int | None:
    raw = (
        item.get("size")
        or item.get("size_bytes")
        or item.get("disk_size")
        or item.get("weights")
    )
    if isinstance(raw, bool) or raw in (None, ""):
        return None
    if isinstance(raw, (int, float)) and raw > 0:
        return int(raw)
    if isinstance(raw, str):
        return parse_size_label(raw)
    return None


def _fetch_family_size(family: str) -> int | None:
    try:
        html = http_get(f"https://ollama.com/library/{quote(family)}", timeout=12.0)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        LOGGER.debug("Ollama library fetch failed for %s: %s", family, exc)
        return _PINNED_DEFAULT_SIZES.get(family)
    return parse_ollama_library_size(html, family) or _PINNED_DEFAULT_SIZES.get(family)


def _with_size(entry: CatalogEntry, size_bytes: int | None) -> CatalogEntry:
    if not size_bytes or entry.size_bytes:
        return entry
    return CatalogEntry(
        name=entry.name,
        display_name=entry.display_name,
        size_bytes=size_bytes,
        installed=entry.installed,
        gated=entry.gated,
        description=entry.description,
        family=entry.family,
        role=entry.role,
        is_family=entry.is_family,
    )


def _enrich_sizes(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    missing = [
        entry
        for entry in entries
        if not entry.size_bytes and (entry.family or entry.name)
    ]
    if not missing:
        return entries
    families = list(dict.fromkeys(entry.family or entry.name for entry in missing))
    sizes: dict[str, int | None] = {}
    workers = min(8, len(families))
    with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
        futures = {
            pool.submit(_fetch_family_size, family): family for family in families
        }
        for future in as_completed(futures):
            family = futures[future]
            try:
                sizes[family] = future.result()
            except Exception:
                LOGGER.debug("Family size lookup failed for %s", family, exc_info=True)
                sizes[family] = _PINNED_DEFAULT_SIZES.get(family)
    return [
        _with_size(entry, sizes.get(entry.family or entry.name))
        for entry in entries
    ]


def _cli_supports_search() -> bool:
    try:
        result = subprocess.run(
            ["ollama", "search", "--help"],
            capture_output=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def parse_ollama_cli_search(output: str) -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    seen: set[str] = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("name") or set(line) <= {"-", " "}:
            continue
        name = line.split()[0]
        if name in seen or name.lower() in {"name", "model"}:
            continue
        seen.add(name)
        entries.append(
            CatalogEntry(
                name=name,
                display_name=name,
                size_bytes=parse_size_label(line),
                family=name.split(":", 1)[0],
                is_family=":" not in name,
            )
        )
    return entries


def _cli_search(query: str) -> list[CatalogEntry]:
    if not _cli_supports_search():
        return []
    command = ["ollama", "search", query] if query.strip() else ["ollama", "search"]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return parse_ollama_cli_search(result.stdout or result.stderr)


def _installed_names() -> set[str]:
    try:
        models = RequirementsSummarizer.list_available_models()
    except Exception:
        LOGGER.debug("Could not list installed Ollama models", exc_info=True)
        return set()
    return {model.name for model in models}


def _with_installed(entries: list[CatalogEntry], installed: set[str]) -> list[CatalogEntry]:
    updated: list[CatalogEntry] = []
    for entry in entries:
        matches = entry.name in installed or any(
            name == entry.name or name.startswith(f"{entry.name}:")
            for name in installed
        )
        updated.append(
            CatalogEntry(
                name=entry.name,
                display_name=entry.display_name,
                size_bytes=entry.size_bytes,
                installed=matches,
                gated=entry.gated,
                description=entry.description,
                family=entry.family,
                role=entry.role,
                is_family=entry.is_family,
            )
        )
    return updated


def _pin_recommended(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    by_name = {entry.name: entry for entry in entries}
    pinned: list[CatalogEntry] = []
    used: set[str] = set()
    for name, role in PINNED_OLLAMA_MODELS:
        match = by_name.get(name)
        if match is None:
            for entry in entries:
                if entry.name == name or entry.name.startswith(f"{name}:"):
                    match = entry
                    break
        if match is None:
            match = CatalogEntry(
                name=name,
                display_name=name,
                family=name,
                role=role,
                is_family=True,
            )
        else:
            match = CatalogEntry(
                name=match.name,
                display_name=match.display_name,
                size_bytes=match.size_bytes,
                installed=match.installed,
                gated=match.gated,
                description=match.description,
                family=match.family or name,
                role=role,
                is_family=match.is_family,
            )
        pinned.append(match)
        used.add(match.name)
    rest = [entry for entry in entries if entry.name not in used]
    return pinned + rest


class OllamaCatalogProvider:
    id = "ollama"
    title = "Write meeting notes"

    def list_models(self, query: str = "") -> list[CatalogEntry]:
        installed = _installed_names()
        entries = self._fetch_search(query)
        if not entries:
            entries = _cli_search(query)
        if not entries and not query.strip():
            entries = [
                CatalogEntry(name=name, display_name=name, family=name, role=role, is_family=True)
                for name, role in PINNED_OLLAMA_MODELS
            ]
        return _enrich_sizes(_pin_recommended(_with_installed(entries, installed)))

    def list_variants(self, family: str) -> list[CatalogEntry]:
        installed = _installed_names()
        html = ""
        try:
            html = http_get(f"https://ollama.com/library/{quote(family)}/tags")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            LOGGER.debug("Ollama tags fetch failed for %s: %s", family, exc)
        entries = parse_ollama_tags_html(html, family) if html else []
        if not entries:
            entries = [
                CatalogEntry(name=family, display_name=f"{family}:latest", family=family)
            ]
        return _with_installed(entries, installed)

    def is_installed(self, name: str) -> bool:
        installed = _installed_names()
        return name in installed or any(
            item == name or item.startswith(f"{name}:") for item in installed
        )

    def download(
        self,
        name: str,
        on_progress: Callable[[DownloadProgress], None] | None,
        cancel_event: Event,
    ) -> None:
        import ollama

        client = ollama.Client()
        layers: dict[str, tuple[int, int]] = {}
        started = time.monotonic()
        stream = client.pull(name, stream=True)
        for event in stream:
            if cancel_event.is_set():
                raise InterruptedError(
                    "Download tracking stopped. Ollama may finish the pull in the background."
                )
            progress = aggregate_pull_progress(layers, event, started)
            if on_progress is not None:
                on_progress(progress)

    def cache_path(self):
        return ollama_models_dir()

    def disk_usage(self):
        return disk_usage_for(self.cache_path())

    def _fetch_search(self, query: str) -> list[CatalogEntry]:
        params = {"q": query, "o": "popular"} if query.strip() else {"o": "popular"}
        url = f"https://ollama.com/search?{urlencode(params)}"
        try:
            payload = http_get(url, accept="application/json, text/html")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            LOGGER.debug("Ollama search fetch failed: %s", exc)
            return []
        stripped = payload.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed = parse_ollama_search_json(json.loads(payload))
            except json.JSONDecodeError:
                parsed = None
            if parsed:
                return parsed
        return parse_ollama_search_html(payload)
