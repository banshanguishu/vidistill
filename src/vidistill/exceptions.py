class VidistillError(Exception):
    """Base exception for all vidistill domain errors."""


class VideoFetchError(VidistillError):
    """Failure fetching video metadata, subtitle, or audio."""


class VideoTooLongError(VideoFetchError):
    """Video duration exceeds configured maximum."""

    def __init__(self, message: str, duration: int):
        super().__init__(message)
        self.duration = duration


class ASRError(VidistillError):
    """Failure transcribing audio."""


class LLMError(VidistillError):
    """Failure summarizing transcript."""


class RenderError(VidistillError):
    """Failure rendering final output file."""


class QueueFullError(VidistillError):
    """Queue is at capacity (10 active jobs)."""


class JobNotFoundError(VidistillError):
    """Job with given id does not exist."""


class JobNotCancellableError(VidistillError):
    """Job cannot be cancelled because it is no longer queued."""


class JobAccessDeniedError(VidistillError):
    """Operation requires the visitor to be the job creator."""
