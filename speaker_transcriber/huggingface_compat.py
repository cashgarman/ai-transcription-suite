from __future__ import annotations

from collections.abc import Callable
from typing import Any


def patch_hf_hub_use_auth_token() -> None:
    """Translate deprecated use_auth_token for pyannote with newer huggingface_hub."""
    import huggingface_hub

    if getattr(huggingface_hub.hf_hub_download, "_speaker_transcriber_patched", False):
        return

    original: Callable[..., Any] = huggingface_hub.hf_hub_download

    def patched(*args: Any, **kwargs: Any) -> Any:
        legacy_token = kwargs.pop("use_auth_token", None)
        if legacy_token is not None and kwargs.get("token") is None:
            kwargs["token"] = legacy_token
        return original(*args, **kwargs)

    patched._speaker_transcriber_patched = True  # type: ignore[attr-defined]
    huggingface_hub.hf_hub_download = patched

    module_names = (
        "pyannote.audio.core.pipeline",
        "pyannote.audio.core.model",
        "pyannote.audio.pipelines.speaker_verification",
    )
    for module_name in module_names:
        try:
            import importlib

            module = importlib.import_module(module_name)
            if hasattr(module, "hf_hub_download"):
                module.hf_hub_download = patched
        except ImportError:
            pass
