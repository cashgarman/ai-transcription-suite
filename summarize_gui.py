#!/usr/bin/env python
"""Deprecated compatibility launcher for the PySide6 application."""

from speaker_transcriber.app import main


if __name__ == "__main__":
    raise SystemExit(main())