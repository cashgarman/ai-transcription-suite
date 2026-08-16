"""Session debug logging (removed after the bug is verified fixed)."""

from __future__ import annotations

import json
import time
from pathlib import Path


_LOG_PATH = Path(__file__).resolve().parents[3] / "debug-f45478.log"
_SESSION = "f45478"


def agent_log(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": _SESSION,
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data,
            "hypothesisId": hypothesis_id,
        }
        with _LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion
