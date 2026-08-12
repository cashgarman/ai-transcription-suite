#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(dirname "$SCRIPT_DIR")
cd "$PROJECT_DIR"

if [ -x ".venv/bin/python" ]; then
    exec .venv/bin/python -m speaker_transcriber.app
fi

exec python3.11 -m speaker_transcriber.app
