from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

LICENSE_PRODUCT = "summit-personal"

# Public half of the Summit license signing keypair. Replace when rotating keys.
EMBEDDED_PUBLIC_KEY_B64 = "KuxHAaEUohBKg7Q2smCv9taZUvkh0pNMn81hD8A/vew="


@dataclass(frozen=True)
class LicensePayload:
    product: str
    email: str
    issued: str


def _canonical_payload(document: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in document.items() if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_license_document(
    document: dict[str, Any],
    *,
    public_key_b64: str = EMBEDDED_PUBLIC_KEY_B64,
) -> LicensePayload | None:
    signature_b64 = document.get("signature")
    if not isinstance(signature_b64, str) or not signature_b64.strip():
        return None
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_b64)
        )
        public_key.verify(
            base64.b64decode(signature_b64),
            _canonical_payload(document),
        )
    except (InvalidSignature, ValueError):
        return None
    product = str(document.get("product", "")).strip()
    email = str(document.get("email", "")).strip()
    issued = str(document.get("issued", "")).strip()
    if product != LICENSE_PRODUCT or not email or not issued:
        return None
    return LicensePayload(product=product, email=email, issued=issued)


def verify_license_bytes(
    data: bytes,
    *,
    public_key_b64: str = EMBEDDED_PUBLIC_KEY_B64,
) -> LicensePayload | None:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict):
        return None
    return verify_license_document(document, public_key_b64=public_key_b64)


def sign_license_document(
    payload: dict[str, Any],
    private_key_b64: str,
) -> dict[str, Any]:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    document = dict(payload)
    document.pop("signature", None)
    private_key = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(private_key_b64)
    )
    signature = private_key.sign(_canonical_payload(document))
    document["signature"] = base64.b64encode(signature).decode("ascii")
    return document
