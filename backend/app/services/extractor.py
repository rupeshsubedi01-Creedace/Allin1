"""Wraps yt-dlp to extract metadata and produce a clean list of formats."""

from __future__ import annotations

from typing import Any

import yt_dlp

from ..config import Settings
from ..schemas import ExtractResponse, FormatOption
from . import errors, platform_detect

_VIDEO_EXT_FALLBACK = {"mp4", "webm", "mkv", "mov", "flv", "avi"}
_AUDIO_EXT_FALLBACK = {"mp3", "m4a", "aac", "wav", "flac", "ogg", "opus"}


def _base_ydl_opts(settings: Settings) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": settings.socket_timeout,
        "nocheckcertificate": False,
        "extract_flat": False,
        "geo_bypass": True,
    }
    if settings.ffmpeg_path:
        opts["ffmpeg_location"] = settings.ffmpeg_path
    return opts


def _human_label(height: int | None, fps: float | None) -> str:
    if not height:
        return "Video"
    label = f"{height}p"
    if fps and fps > 30:
        label += f"{int(fps)}"
    return label


def _build_video_formats(raw_formats: list[dict[str, Any]]) -> list[FormatOption]:
    by_height: dict[int, dict[str, Any]] = {}
    for fmt in raw_formats:
        vcodec = fmt.get("vcodec")
        if not vcodec or vcodec == "none":
            continue
        height = fmt.get("height")
        if not height:
            continue
        tbr = fmt.get("tbr") or 0
        current = by_height.get(height)
        if current is None or (current.get("tbr") or 0) < tbr:
            by_height[height] = fmt

    options: list[FormatOption] = []
    for height, fmt in sorted(by_height.items(), key=lambda kv: kv[0], reverse=True):
        acodec = fmt.get("acodec")
        requires_merge = not acodec or acodec == "none"
        width = fmt.get("width")
        resolution = fmt.get("resolution") or (f"{width}x{height}" if width else None)
        options.append(
            FormatOption(
                format_id=str(fmt.get("format_id")),
                type="video",
                label=_human_label(height, fmt.get("fps")),
                ext=fmt.get("ext") or "mp4",
                resolution=resolution,
                fps=fmt.get("fps"),
                vcodec=fmt.get("vcodec"),
                acodec=acodec,
                filesize=fmt.get("filesize") or fmt.get("filesize_approx"),
                requires_merge=requires_merge,
            )
        )
    return options


def _build_audio_formats(raw_formats: list[dict[str, Any]]) -> list[FormatOption]:
    audio_only = [
        fmt
        for fmt in raw_formats
        if (fmt.get("vcodec") in (None, "none")) and fmt.get("acodec") not in (None, "none")
    ]
    audio_only.sort(key=lambda f: f.get("abr") or 0, reverse=True)
    options: list[FormatOption] = []
    seen_abr: set[int] = set()
    for fmt in audio_only[:6]:
        abr = round(fmt.get("abr") or 0)
        if abr in seen_abr:
            continue
        seen_abr.add(abr)
        ext_label = fmt.get("ext", "audio").upper()
        label = f"{ext_label} · {abr}kbps" if abr else ext_label
        options.append(
            FormatOption(
                format_id=str(fmt.get("format_id")),
                type="audio",
                label=label,
                ext=fmt.get("ext") or "m4a",
                abr=fmt.get("abr"),
                acodec=fmt.get("acodec"),
                filesize=fmt.get("filesize") or fmt.get("filesize_approx"),
                requires_merge=False,
            )
        )
    return options


def _mp3_option() -> FormatOption:
    return FormatOption(
        format_id="mp3",
        type="audio",
        label="MP3 (audio only, 192kbps)",
        ext="mp3",
        abr=192,
        requires_merge=False,
    )


def _direct_file_options(info: dict[str, Any]) -> list[FormatOption]:
    """Options for a direct media link (or any extraction without codec data).

    For direct file URLs yt-dlp reports a single format whose ``vcodec`` and
    ``acodec`` are unknown, so the per-resolution/per-bitrate builders cannot
    classify it. Fall back to exposing the original file itself, using the
    top-level info dict.
    """
    ext = (info.get("ext") or "").lower()
    format_id = str(info.get("format_id") or "0")
    filesize = info.get("filesize") or info.get("filesize_approx")
    option: FormatOption
    if ext in _AUDIO_EXT_FALLBACK:
        option = FormatOption(
            format_id=format_id,
            type="audio",
            label=f"Original audio ({ext.upper()})",
            ext=ext,
            abr=info.get("abr"),
            acodec=info.get("acodec"),
            filesize=filesize,
        )
    else:
        option = FormatOption(
            format_id=format_id,
            type="video",
            label=f"Original file ({ext.upper()})" if ext else "Original file",
            ext=ext or "mp4",
            resolution=info.get("resolution"),
            fps=info.get("fps"),
            vcodec=info.get("vcodec"),
            acodec=info.get("acodec"),
            filesize=filesize,
        )
    return [option, _mp3_option()]


def build_formats(info: dict[str, Any]) -> list[FormatOption]:
    raw_formats = info.get("formats") or []
    options = _build_video_formats(raw_formats)
    options.extend(_build_audio_formats(raw_formats))
    if not options:
        # Direct-file extraction (or formats with no usable codec metadata):
        # without this fallback only the synthetic MP3 entry would remain.
        return _direct_file_options(info)
    options.append(_mp3_option())
    return options


def extract_info(url: str, settings: Settings) -> ExtractResponse:
    if not platform_detect.is_valid_url(url):
        raise errors.InvalidURLError()

    platform = platform_detect.detect_platform(url)
    opts = _base_ydl_opts(settings)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise errors.classify_exception(exc) from exc
    except Exception as exc:  # noqa: BLE001 - translate any unexpected failure
        raise errors.classify_exception(exc) from exc

    if info is None:
        raise errors.ExtractionError("No information could be extracted from this link.")

    if "entries" in info and info.get("entries"):
        # A playlist / channel link — take the first playable entry.
        info = next((e for e in info["entries"] if e), info)

    formats = build_formats(info)
    return ExtractResponse(
        title=info.get("title") or "Untitled media",
        webpage_url=info.get("webpage_url") or url,
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        uploader=info.get("uploader") or info.get("channel"),
        platform_key=platform.key,
        platform_label=platform.label,
        platform_icon=platform.icon,
        formats=formats,
    )
