import pytest

from vidistill.exceptions import (
    ASRError,
    JobAccessDeniedError,
    JobNotCancellableError,
    JobNotFoundError,
    LLMError,
    QueueFullError,
    RenderError,
    VideoFetchError,
    VideoTooLongError,
    VidistillError,
)


def test_hierarchy():
    assert issubclass(VideoFetchError, VidistillError)
    assert issubclass(ASRError, VidistillError)
    assert issubclass(LLMError, VidistillError)
    assert issubclass(RenderError, VidistillError)
    assert issubclass(VideoTooLongError, VideoFetchError)


def test_exception_message():
    err = VideoFetchError("video deleted")
    assert str(err) == "video deleted"


def test_video_too_long_carries_duration():
    err = VideoTooLongError("3000 seconds exceeds limit", duration=3000)
    assert err.duration == 3000


def test_v2_exceptions_inherit_vidistill_error():
    for cls in (QueueFullError, JobNotFoundError, JobNotCancellableError, JobAccessDeniedError):
        assert issubclass(cls, VidistillError)
        assert issubclass(cls, Exception)
