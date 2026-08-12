class SpeakerTranscriberError(Exception):
    """Base class for user-facing application errors."""


class ProcessingCancelled(SpeakerTranscriberError):
    """Raised when cancellation is observed at a safe boundary."""

    def __init__(self, partial_result=None) -> None:
        super().__init__("Processing was cancelled.")
        self.partial_result = partial_result


class MediaError(SpeakerTranscriberError):
    """Raised when media cannot be inspected or converted."""


class AuthenticationError(SpeakerTranscriberError):
    """Raised when a gated model cannot be accessed."""


class NoSpeechError(SpeakerTranscriberError):
    """Raised when transcription produces no speech."""
