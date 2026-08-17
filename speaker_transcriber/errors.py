class SpeakerTranscriberError(Exception):
    """Base class for user-facing application errors."""


class TrialLimitReason:
    MULTI_FILE = "multi_file"
    DURATION_CONSENT = "duration_consent"


class TrialLimitError(SpeakerTranscriberError):
    """Raised when trial restrictions block an operation."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        full_duration_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.full_duration_seconds = full_duration_seconds


class ProcessingCancelled(SpeakerTranscriberError):
    """Raised when cancellation is observed at a safe boundary."""

    def __init__(self, partial_result=None) -> None:
        super().__init__("Processing was cancelled.")
        self.partial_result = partial_result


class MediaError(SpeakerTranscriberError):
    """Raised when media cannot be inspected or converted."""


class TtsError(SpeakerTranscriberError):
    """Raised when native text-to-speech fails."""


class AuthenticationError(SpeakerTranscriberError):
    """Raised when a gated model cannot be accessed."""


class NoSpeechError(SpeakerTranscriberError):
    """Raised when transcription produces no speech."""
