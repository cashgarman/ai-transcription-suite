from __future__ import annotations

import logging
import sys
from pathlib import Path


LOGGER = logging.getLogger("speaker_transcriber.prompts")

PROMPT_FILENAMES = {
    "system": "system.txt",
    "chunk": "chunk.txt",
    "merge": "merge.txt",
    "validate": "validate.txt",
    "continue": "continue.txt",
    "format": "format.txt",
}

_cache: dict[str, str] = {}


def prompts_dir() -> Path:
    package_dir = Path(__file__).resolve().parent
    if package_dir.is_dir() and (package_dir / "system.txt").is_file():
        return package_dir

    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    if getattr(sys, "frozen", False):
        install_dir = Path(sys.executable).resolve().parent
        roots.extend((install_dir / "_internal", install_dir))

    for root in roots:
        candidate = root / "speaker_transcriber" / "prompts"
        if (candidate / "system.txt").is_file():
            return candidate
    return package_dir


def load_prompts() -> dict[str, str]:
    directory = prompts_dir()
    loaded: dict[str, str] = {}
    missing: list[str] = []
    for key, filename in PROMPT_FILENAMES.items():
        path = directory / filename
        if not path.is_file():
            missing.append(str(path))
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            missing.append(f"{path} (empty)")
            continue
        loaded[key] = text
    if missing:
        raise FileNotFoundError(
            "Missing or empty summarization prompt file(s):\n" + "\n".join(missing)
        )
    _cache.clear()
    _cache.update(loaded)
    LOGGER.info("Loaded %d prompt(s) from %s", len(loaded), directory)
    return dict(_cache)


def reload_prompts() -> dict[str, str]:
    return load_prompts()


def get_prompt(name: str) -> str:
    if name not in _cache:
        load_prompts()
    try:
        return _cache[name]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt '{name}'") from exc
