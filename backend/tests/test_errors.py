from backend.app.services.errors import (
    DownloadTimeoutError,
    FFmpegMissingError,
    GeoBlockedError,
    MediaUnavailableError,
    NetworkError,
    UnsupportedURLError,
    classify_exception,
)


def test_classify_private_video():
    err = classify_exception(Exception("ERROR: Private video. Sign in if you've been granted access"))
    assert isinstance(err, MediaUnavailableError)


def test_classify_removed_video():
    err = classify_exception(Exception("ERROR: Video unavailable. This video has been removed"))
    assert isinstance(err, MediaUnavailableError)


def test_classify_geo_blocked():
    err = classify_exception(Exception("The uploader has not made this video available in your country"))
    assert isinstance(err, GeoBlockedError)


def test_classify_timeout():
    err = classify_exception(TimeoutError("The read operation timed out"))
    assert isinstance(err, DownloadTimeoutError)


def test_classify_network_error():
    err = classify_exception(ConnectionError("Network is unreachable"))
    assert isinstance(err, NetworkError)


def test_classify_ffmpeg_missing():
    err = classify_exception(Exception("ffmpeg not found. Please install"))
    assert isinstance(err, FFmpegMissingError)


def test_classify_unsupported_url():
    err = classify_exception(Exception("Unsupported URL: foo://bar"))
    assert isinstance(err, UnsupportedURLError)


def test_classify_unknown_falls_back_generic():
    err = classify_exception(Exception("Something completely unexpected happened"))
    assert err.code == "extraction_failed"
