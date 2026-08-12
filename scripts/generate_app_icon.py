"""Render Summit application icons used by the splash, window, and EXE."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from speaker_transcriber.ui.branding import (
    assets_dir,
    write_summit_ico,
)


def main() -> int:
    application = QApplication(sys.argv[:1])
    directory = assets_dir()
    ico_path = directory / "summit.ico"
    write_summit_ico(ico_path)
    print(f"wrote {ico_path}")

    application.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
