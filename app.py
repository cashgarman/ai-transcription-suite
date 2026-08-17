#!/usr/bin/env python
"""Launcher that always runs the GUI with the project's own environment.

When invoked with an interpreter that lacks the app's dependencies (for
example a stale venv or the system Python), it re-launches itself with the
project's .venv interpreter instead of crashing with ModuleNotFoundError.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent
_VENV_INTERPRETERS = (
    _PROJECT_DIR / ".venv" / "Scripts" / "python.exe",
    _PROJECT_DIR / ".venv" / "bin" / "python",
)


def _dependencies_available() -> bool:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        return False
    return True


def _project_interpreter() -> Path | None:
    """The .venv interpreter, unless it is the one already running."""
    current = Path(sys.executable).resolve()
    for candidate in _VENV_INTERPRETERS:
        if candidate.is_file() and candidate.resolve() != current:
            return candidate
    return None


def main() -> int:
    try:
        if _dependencies_available():
            from speaker_transcriber.app import main as run_app

            return run_app()
        interpreter = _project_interpreter()
        if interpreter is None:
            raise SystemExit(
                "This Python environment is missing the app's dependencies "
                "(PySide6), and no usable .venv was found next to app.py.\n"
                "Create one from the project directory:\n"
                "  py -3.12 -m venv .venv\n"
                "  .venv\\Scripts\\pip install -e ."
            )
        command = [str(interpreter), str(_PROJECT_DIR / "app.py"), *sys.argv[1:]]
        return subprocess.run(command).returncode
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
