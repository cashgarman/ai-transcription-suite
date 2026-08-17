from __future__ import annotations

MIN_PLAYBACK_RATE = 0.25
MAX_PLAYBACK_RATE = 4.0
PLAYBACK_RATE_STEP = 0.05


def clamp_playback_rate(rate: float) -> float:
    snapped = round(float(rate) / PLAYBACK_RATE_STEP) * PLAYBACK_RATE_STEP
    clamped = min(MAX_PLAYBACK_RATE, max(MIN_PLAYBACK_RATE, snapped))
    return round(clamped, 2)


def atempo_filter_graph(rate: float) -> str | None:
    """Pitch-preserving FFmpeg atempo chain. Each stage stays in 0.5–2.0."""
    tempo = clamp_playback_rate(rate)
    if abs(tempo - 1.0) < 1e-6:
        return None
    factors: list[float] = []
    remaining = tempo
    while remaining > 2.0 + 1e-9:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5 - 1e-9:
        factors.append(0.5)
        remaining /= 0.5
    if abs(remaining - 1.0) > 1e-6:
        factors.append(remaining)
    if not factors:
        return None
    return ",".join(f"atempo={factor:.6g}" for factor in factors)
