#!/usr/bin/env python3
"""Sign a Summit license file for offline activation."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from speaker_transcriber.license_verify import LICENSE_PRODUCT, sign_license_document

DEFAULT_PRIVATE_KEY_B64 = os.environ.get(
    "SUMMIT_LICENSE_PRIVATE_KEY",
    "ej8AhoZOcmSLEVvQxft2oxW1eD9VTJYxHZXaa+kzGM4=",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sign a Summit license.summit file.")
    parser.add_argument("--email", required=True, help="Licensee email address")
    parser.add_argument("--issued", required=True, help="Issue date (YYYY-MM-DD)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("license.summit"),
        help="Output path (default: license.summit)",
    )
    parser.add_argument(
        "--private-key",
        default=DEFAULT_PRIVATE_KEY_B64,
        help="Base64 Ed25519 private key (prefer SUMMIT_LICENSE_PRIVATE_KEY env var)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    document = sign_license_document(
        {
            "product": LICENSE_PRODUCT,
            "email": args.email.strip(),
            "issued": args.issued.strip(),
        },
        args.private_key.strip(),
    )
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
