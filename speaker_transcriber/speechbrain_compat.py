from __future__ import annotations


def patch_speechbrain_lazy_modules() -> None:
    """Prevent inspect.stack() from eagerly loading optional SpeechBrain integrations."""
    try:
        from speechbrain.utils.importutils import LazyModule
    except ImportError:
        return

    if getattr(LazyModule, "_speaker_transcriber_patched", False):
        return

    original_getattr = LazyModule.__getattr__

    def patched_getattr(self, name: str):
        if name == "__file__":
            return None
        return original_getattr(self, name)

    patched_getattr._speaker_transcriber_patched = True  # type: ignore[attr-defined]
    LazyModule.__getattr__ = patched_getattr  # type: ignore[method-assign]
    LazyModule._speaker_transcriber_patched = True
