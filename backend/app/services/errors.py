"""Application level error taxonomy.

yt-dlp (and the network stack underneath it) can fail in many different
ways. We translate every failure into one of a small set of ``AppError``
subclasses that carry an HTTP status code, a machine readable ``code`` and a
human friendly ``message`` that the frontend can show directly to the user.
"""

from __future__ import annotations

import socket
from http.client import RemoteDisconnected
from urllib.error import URLError


class AppError(Exception):
    """Base class for all user-facing errors."""

    code = "unknown_error"
    status_code = 500
    default_message = "Something went wrong. Please try again."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.default_message)
        self.message = message or self.default_message

    def to_dict(self) -> dict:
        return {"error_code": self.code, "message": self.message}


class InvalidURLError(AppError):
    code = "invalid_url"
    status_code = 400
    default_message = "That link doesn't look like a valid URL. Please check it and try again."


class UnsupportedURLError(AppError):
    code = "unsupported_url"
    status_code = 422
    default_message = "This link isn't supported by any known extractor."


class MediaUnavailableError(AppError):
    code = "media_unavailable"
    status_code = 404
    default_message = (
        "This media is private, has been removed, or requires login and can't be downloaded."
    )


class GeoBlockedError(AppError):
    code = "geo_blocked"
    status_code = 451
    default_message = "This media is not available in the server's region (geo-blocked)."


class DownloadTimeoutError(AppError):
    code = "timeout"
    status_code = 504
    default_message = "The request timed out while talking to the source site. Please try again."


class NetworkError(AppError):
    code = "network_error"
    status_code = 502
    default_message = "A network error occurred while fetching the media. Check your connection."


class FFmpegMissingError(AppError):
    code = "ffmpeg_missing"
    status_code = 500
    default_message = (
        "ffmpeg is not installed on the server, so this format (which needs audio/video "
        "merging or MP3 conversion) cannot be processed."
    )


class ExtractionError(AppError):
    code = "extraction_failed"
    status_code = 502
    default_message = "Could not read information from this link."


class JobNotFoundError(AppError):
    code = "job_not_found"
    status_code = 404
    default_message = "This download job does not exist or has expired."


class JobAlreadyFinishedError(AppError):
    code = "job_already_finished"
    status_code = 409
    default_message = "This download has already finished."


class HistoryItemNotFoundError(AppError):
    code = "history_item_not_found"
    status_code = 404
    default_message = "This history entry no longer exists."


_PRIVATE_MARKERS = (
    "private video",
    "private account",
    "requires you to be logged",
    "login required",
    "sign in",
    "this is a private",
    "rate-limit reached",
)

_REMOVED_MARKERS = (
    "video unavailable",
    "video has been removed",
    "has been removed",
    "no longer available",
    "does not exist",
    "content isn't available",
    "page not found",
    "account not found",
    "media not found",
    "this content isn't available",
)

_GEO_MARKERS = (
    "not available in your country",
    "not available on this app and website in your country",
    "blocked it in your country",
    "geo restricted",
    "geo-restricted",
    "the uploader has not made this video available in your country",
)

_UNSUPPORTED_MARKERS = (
    "unsupported url",
    "no video formats found",
    "unable to extract",
)

_FFMPEG_MARKERS = (
    "ffmpeg not found",
    "ffprobe/avprobe and ffmpeg/avconv not found",
    "postprocessing: ffmpeg",
    "you need to install ffmpeg",
)

_TIMEOUT_MARKERS = ("timed out", "timeout")

_NETWORK_MARKERS = (
    "network is unreachable",
    "name or service not known",
    "connection reset",
    "connection refused",
    "temporary failure in name resolution",
    "failed to establish a new connection",
    "no address associated with hostname",
    "remote end closed connection",
    # TLS/SSL level failures (yt-dlp wraps these in DownloadError, which is
    # not an OSError, so they must be matched by message).
    "tls/ssl connection has been closed",
    "ssl connection has been closed",
    "connection aborted",
    "connection broken",
    "incomplete read",
    "eof occurred in violation",
    "certificate verify failed",
)


def classify_exception(exc: BaseException) -> AppError:
    """Map a raw exception (typically from yt-dlp) to an ``AppError``."""

    if isinstance(exc, AppError):
        return exc

    message = str(exc).strip()
    lowered = message.lower()

    if isinstance(exc, (socket.timeout, TimeoutError)) or any(m in lowered for m in _TIMEOUT_MARKERS):
        return DownloadTimeoutError(f"Timed out while contacting the source site: {message or 'no response'}")

    if any(m in lowered for m in _FFMPEG_MARKERS):
        return FFmpegMissingError()

    if any(m in lowered for m in _GEO_MARKERS):
        return GeoBlockedError()

    if any(m in lowered for m in _PRIVATE_MARKERS):
        return MediaUnavailableError("This media is private or requires login.")

    if any(m in lowered for m in _REMOVED_MARKERS):
        return MediaUnavailableError("This media has been removed or no longer exists.")

    if any(m in lowered for m in _UNSUPPORTED_MARKERS):
        return UnsupportedURLError()

    if isinstance(exc, (URLError, RemoteDisconnected, ConnectionError, OSError)) or any(
        m in lowered for m in _NETWORK_MARKERS
    ):
        # Keep only the first line (trimmed) so users don't see yt-dlp's
        # multi-line "please report this issue" boilerplate.
        trimmed = message.splitlines()[0][:200] if message else "connection lost"
        return NetworkError(f"Network error while downloading: {trimmed}")

    # Fall back to a generic extraction error but keep the original (trimmed) message
    # so power-users can still see what yt-dlp reported.
    trimmed = message.splitlines()[0][:300] if message else ExtractionError.default_message
    return ExtractionError(trimmed)
