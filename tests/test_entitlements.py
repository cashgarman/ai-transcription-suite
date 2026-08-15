from __future__ import annotations

import json
from pathlib import Path

import pytest

from speaker_transcriber import entitlements
from speaker_transcriber.config import purchase_url
from speaker_transcriber.entitlements import (
    TRIAL_MAX_DURATION_SECONDS,
    import_license,
    is_licensed,
    set_dev_mode_override,
    validate_trial_duration_consent,
    validate_trial_file_count,
)
from speaker_transcriber.errors import TrialLimitError, TrialLimitReason
from speaker_transcriber.license_verify import (
    EMBEDDED_PUBLIC_KEY_B64,
    sign_license_document,
    verify_license_bytes,
)


PRIVATE_KEY_B64 = "ej8AhoZOcmSLEVvQxft2oxW1eD9VTJYxHZXaa+kzGM4="


@pytest.fixture(autouse=True)
def reset_entitlements(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(entitlements, "_dev_mode_override", None)
    monkeypatch.delenv("SUMMIT_DEV_UNLIMITED", raising=False)
    monkeypatch.setattr(
        entitlements,
        "license_file_path",
        lambda: tmp_path / "license.summit",
    )


def test_purchase_url_default() -> None:
    assert purchase_url().endswith("/#pricing")


def test_trial_rejects_multiple_files() -> None:
    paths = [Path("a.wav"), Path("b.wav")]
    with pytest.raises(TrialLimitError) as exc:
        validate_trial_file_count(paths)
    assert exc.value.reason == TrialLimitReason.MULTI_FILE


def test_trial_allows_single_short_file() -> None:
    validate_trial_file_count([Path("a.wav")])
    validate_trial_duration_consent(599.0, None)


def test_trial_duration_requires_consent_without_cap() -> None:
    with pytest.raises(TrialLimitError) as exc:
        validate_trial_duration_consent(601.0, None)
    assert exc.value.reason == TrialLimitReason.DURATION_CONSENT
    assert "--truncate-trial" not in str(exc.value)


def test_duration_consent_cli_message_mentions_truncate_flag() -> None:
    from speaker_transcriber.entitlements import duration_consent_error_message

    message = duration_consent_error_message(601.0, for_cli=True)
    assert "--truncate-trial" in message


def test_trial_duration_allows_truncation_cap() -> None:
    validate_trial_duration_consent(900.0, TRIAL_MAX_DURATION_SECONDS)


def test_dev_override_simulates_license(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entitlements, "dev_tools_enabled", lambda: True)
    set_dev_mode_override(True)
    assert is_licensed() is True
    validate_trial_file_count([Path("a.wav"), Path("b.wav")])


def test_valid_signed_license_unlocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document = sign_license_document(
        {
            "product": "summit-personal",
            "email": "user@example.com",
            "issued": "2026-08-15",
        },
        PRIVATE_KEY_B64,
    )
    license_path = tmp_path / "license.summit"
    license_path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(entitlements, "license_file_path", lambda: license_path)
    assert verify_license_bytes(license_path.read_bytes()) is not None
    assert is_licensed() is True


def test_tampered_license_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document = sign_license_document(
        {
            "product": "summit-personal",
            "email": "user@example.com",
            "issued": "2026-08-15",
        },
        PRIVATE_KEY_B64,
    )
    document["email"] = "attacker@example.com"
    license_path = tmp_path / "license.summit"
    license_path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(entitlements, "license_file_path", lambda: license_path)
    assert is_licensed() is False


def test_import_license_writes_verified_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    document = sign_license_document(
        {
            "product": "summit-personal",
            "email": "buyer@example.com",
            "issued": "2026-08-15",
        },
        PRIVATE_KEY_B64,
    )
    source = tmp_path / "incoming.summit"
    source.write_text(json.dumps(document), encoding="utf-8")
    destination = tmp_path / "license.summit"
    monkeypatch.setattr(entitlements, "license_file_path", lambda: destination)
    import_license(source)
    assert destination.is_file()
    assert verify_license_bytes(destination.read_bytes()) is not None


def test_embedded_public_key_matches_private_fixture() -> None:
    document = sign_license_document(
        {
            "product": "summit-personal",
            "email": "check@example.com",
            "issued": "2026-08-15",
        },
        PRIVATE_KEY_B64,
    )
    payload = json.dumps(document).encode("utf-8")
    assert verify_license_bytes(payload, public_key_b64=EMBEDDED_PUBLIC_KEY_B64) is not None
