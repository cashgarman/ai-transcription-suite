from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from speaker_transcriber.config import license_file_path, purchase_url
from speaker_transcriber.errors import TrialLimitError, TrialLimitReason
from speaker_transcriber.export.common import clock_timestamp
from speaker_transcriber.license_verify import verify_license_bytes

TRIAL_MAX_FILES = 1
TRIAL_MAX_DURATION_SECONDS = 600.0

_dev_mode_override: bool | None = None
_cached_license_path: Path | None = None


@dataclass(frozen=True)
class Entitlements:
    licensed: bool
    max_files: int
    max_duration_seconds: float | None


def dev_tools_enabled() -> bool:
    if os.environ.get("SUMMIT_DEV_TOOLS", "").strip().lower() in {"1", "true", "yes"}:
        return True
    if os.environ.get("SUMMIT_DEV_UNLIMITED", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return not getattr(sys, "frozen", False)


def set_dev_mode_override(simulate_licensed: bool | None) -> None:
    global _dev_mode_override
    _dev_mode_override = simulate_licensed


def dev_mode_override() -> bool | None:
    return _dev_mode_override


def toggle_dev_mode_override() -> bool:
    global _dev_mode_override
    if _dev_mode_override is None:
        _dev_mode_override = not _verify_license_file()
    else:
        _dev_mode_override = not _dev_mode_override
    return is_licensed()


def dev_mode_label() -> str:
    override = _dev_mode_override
    if override is True:
        return "Licensed (F12 test)"
    if override is False:
        return "Trial (F12 test)"
    if _verify_license_file():
        return "Licensed"
    return "Trial"


def entitlements_mode_display() -> str:
    label = dev_mode_label()
    if dev_tools_enabled():
        return f"Mode: {label} · F12"
    return f"Mode: {label}"


def entitlements_for_app() -> Entitlements:
    if is_licensed():
        return Entitlements(
            licensed=True,
            max_files=0,
            max_duration_seconds=None,
        )
    return Entitlements(
        licensed=False,
        max_files=TRIAL_MAX_FILES,
        max_duration_seconds=TRIAL_MAX_DURATION_SECONDS,
    )


def is_licensed() -> bool:
    if os.environ.get("SUMMIT_DEV_UNLIMITED", "").strip().lower() in {"1", "true", "yes"}:
        return True
    if dev_tools_enabled() and _dev_mode_override is not None:
        return _dev_mode_override
    return _verify_license_file()


def _verify_license_file(path: Path | None = None) -> bool:
    license_path = path or license_file_path()
    if not license_path.is_file():
        return False
    try:
        payload = verify_license_bytes(license_path.read_bytes())
    except OSError:
        return False
    return payload is not None


def load_license() -> Path | None:
    path = license_file_path()
    if _verify_license_file(path):
        return path
    return None


def import_license(source: Path) -> Path:
    if not source.is_file():
        raise ValueError(f"License file not found: {source}")
    payload = verify_license_bytes(source.read_bytes())
    if payload is None:
        raise ValueError("The selected file is not a valid Summit license.")
    destination = license_file_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    global _cached_license_path
    _cached_license_path = destination
    if dev_tools_enabled():
        set_dev_mode_override(None)
    return destination


def multi_file_error_message() -> str:
    return (
        "The trial transcribes one recording at a time. Summit can merge several "
        "files from the same meeting — for example, separate Zoom segments or a "
        "video plus its audio backup — but multi-file merge is included in the "
        "Personal license."
    )


def duration_consent_error_message(
    full_duration_seconds: float,
    *,
    for_cli: bool = False,
) -> str:
    full = clock_timestamp(full_duration_seconds)
    limit = clock_timestamp(TRIAL_MAX_DURATION_SECONDS, milliseconds=False)
    if for_cli:
        return (
            f"This recording is {full}. The free trial can transcribe up to {limit}. "
            f"Re-run with --truncate-trial to process the first {limit}, or upgrade "
            f"for the full recording. Upgrade: {purchase_url()}"
        )
    return (
        f"This recording is {full}. The trial can transcribe the first {limit} only."
    )


def validate_trial_file_count(paths: list[Path]) -> None:
    if is_licensed():
        return
    if len(paths) <= TRIAL_MAX_FILES:
        return
    raise TrialLimitError(
        multi_file_error_message(),
        reason=TrialLimitReason.MULTI_FILE,
    )


def validate_trial_duration_consent(
    full_duration_seconds: float,
    max_input_duration_seconds: float | None,
) -> None:
    if is_licensed():
        return
    if full_duration_seconds <= TRIAL_MAX_DURATION_SECONDS:
        return
    if (
        max_input_duration_seconds is not None
        and max_input_duration_seconds <= TRIAL_MAX_DURATION_SECONDS
    ):
        return
    raise TrialLimitError(
        duration_consent_error_message(full_duration_seconds),
        reason=TrialLimitReason.DURATION_CONSENT,
        full_duration_seconds=full_duration_seconds,
    )


def trial_hint_text() -> str:
    return (
        "Trial: one file, up to 10 minutes. Personal unlocks multi-file merge "
        "and unlimited length."
    )


def partial_transcript_message(
    processed_seconds: float,
    full_seconds: float,
) -> str:
    processed = clock_timestamp(processed_seconds)
    full = clock_timestamp(full_seconds)
    return (
        f"Trial transcript — first {processed} of {full}. "
        "Upgrade for the full recording."
    )
