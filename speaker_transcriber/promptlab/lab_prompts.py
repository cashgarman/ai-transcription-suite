"""Loader for the Prompt Lab's own prompts.

Same convention as the app's summarization prompts: plain `.txt` files on disk,
cached in memory, reloadable without a restart. Keeping the lab's prompts in
files means the generator, judge, and optimizer can themselves be tuned by
hand between runs.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


LOGGER = logging.getLogger("speaker_transcriber.promptlab.prompts")

LAB_PROMPT_FILENAMES = {
    "scenario_dialogue": "scenario_dialogue.txt",
    "freeform_transcript": "freeform_transcript.txt",
    "judge_grounded": "judge_grounded.txt",
    "judge_reference_free": "judge_reference_free.txt",
    "optimizer": "optimizer.txt",
}

_cache: dict[str, str] = {}


def _looks_like_prompts_dir(candidate: Path) -> bool:
    return (candidate / LAB_PROMPT_FILENAMES["judge_grounded"]).is_file()


def lab_prompts_dir() -> Path:
    package_dir = Path(__file__).resolve().parent / "prompts"
    if _looks_like_prompts_dir(package_dir):
        return package_dir

    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    if getattr(sys, "frozen", False):
        install_dir = Path(sys.executable).resolve().parent
        roots.extend((install_dir / "_internal", install_dir))
    for root in roots:
        candidate = root / "speaker_transcriber" / "promptlab" / "prompts"
        if _looks_like_prompts_dir(candidate):
            return candidate
    return package_dir


def load_lab_prompts() -> dict[str, str]:
    directory = lab_prompts_dir()
    loaded: dict[str, str] = {}
    missing: list[str] = []
    for key, filename in LAB_PROMPT_FILENAMES.items():
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
            "Missing or empty Prompt Lab prompt file(s):\n" + "\n".join(missing)
        )
    _cache.clear()
    _cache.update(loaded)
    LOGGER.info("Loaded %d Prompt Lab prompt(s) from %s", len(loaded), directory)
    return dict(_cache)


def reload_lab_prompts() -> dict[str, str]:
    return load_lab_prompts()


def get_lab_prompt(name: str) -> str:
    if name not in _cache:
        load_lab_prompts()
    try:
        return _cache[name]
    except KeyError as exc:
        raise KeyError(f"Unknown Prompt Lab prompt '{name}'") from exc


def set_lab_prompt(name: str, text: str) -> None:
    """Override a lab prompt for the current process only."""
    if name not in LAB_PROMPT_FILENAMES:
        raise KeyError(f"Unknown Prompt Lab prompt '{name}'")
    _cache[name] = str(text)


def save_lab_prompt(name: str, text: str) -> Path:
    """Write a lab prompt back to its file and refresh the cache."""
    if name not in LAB_PROMPT_FILENAMES:
        raise KeyError(f"Unknown Prompt Lab prompt '{name}'")
    body = str(text).strip()
    if not body:
        raise ValueError("A prompt cannot be empty.")
    path = lab_prompts_dir() / LAB_PROMPT_FILENAMES[name]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body + "\n", encoding="utf-8")
    _cache[name] = body
    return path
