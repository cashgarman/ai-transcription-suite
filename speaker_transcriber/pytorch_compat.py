from __future__ import annotations

from collections.abc import Callable
from typing import Any


def patch_torch_load_weights_only() -> None:
    """Default torch.load to weights_only=False for pyannote/lightning checkpoints."""
    import torch

    if getattr(torch.load, "_speaker_transcriber_patched", False):
        return

    original: Callable[..., Any] = torch.load

    def patched(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("weights_only") is None:
            kwargs["weights_only"] = False
        return original(*args, **kwargs)

    patched._speaker_transcriber_patched = True  # type: ignore[attr-defined]
    torch.load = patched
