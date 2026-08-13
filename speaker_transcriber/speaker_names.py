from __future__ import annotations

import re


_GENERIC_SPEAKER_ID = re.compile(r"^SPEAKER_\d+$", re.IGNORECASE)
_GENERIC_SPEAKER_DISPLAY = re.compile(r"^Speaker\s+\d+$", re.IGNORECASE)


def is_generic_speaker_name(name: str, label: str | None = None) -> bool:
    stripped = (name or "").strip()
    if not stripped:
        return True
    if _GENERIC_SPEAKER_ID.fullmatch(stripped) or _GENERIC_SPEAKER_DISPLAY.fullmatch(
        stripped
    ):
        return True
    if label and stripped == label and _GENERIC_SPEAKER_ID.fullmatch(label):
        return True
    return False


def custom_speaker_names(speakers: dict[str, str]) -> dict[str, str]:
    return {
        str(label): str(name).strip()
        for label, name in speakers.items()
        if str(name).strip() and not is_generic_speaker_name(str(name), str(label))
    }


def merge_cached_speaker_names(
    current: dict[str, str],
    existing: dict[str, str] | None = None,
) -> dict[str, str]:
    existing_custom = custom_speaker_names(existing or {})
    incoming_custom = custom_speaker_names(current)
    merged: dict[str, str] = {}
    for label in current:
        key = str(label)
        if key in incoming_custom:
            merged[key] = incoming_custom[key]
        elif key in existing_custom:
            merged[key] = existing_custom[key]
    return merged


def apply_cached_speaker_names(
    speakers: dict[str, str],
    existing: dict[str, str] | None = None,
) -> dict[str, str]:
    merged = {str(label): str(name) for label, name in speakers.items()}
    merged.update(merge_cached_speaker_names(merged, existing))
    return merged


def apply_display_names_to_text(text: str, speakers: dict[str, str]) -> str:
    updated = text
    custom = custom_speaker_names(speakers)
    ordered = sorted(str(label) for label in speakers)
    replacements: list[tuple[str, str]] = []
    for index, label in enumerate(ordered, start=1):
        name = custom.get(label)
        if not name:
            continue
        replacements.append((label, name))
        default_name = f"Speaker {index}"
        if default_name != name:
            replacements.append((default_name, name))
    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    for source, name in replacements:
        updated = re.sub(rf"\b{re.escape(source)}\b", name, updated)
    return updated
