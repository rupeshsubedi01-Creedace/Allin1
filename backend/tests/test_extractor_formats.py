"""Unit tests for format list construction in the extractor service."""

from __future__ import annotations

from backend.app.services.extractor import build_formats


def test_direct_video_file_exposes_original_and_mp3():
    # Shape of what yt-dlp returns for a direct .mp4 URL: a single format
    # with no codec/resolution metadata.
    info = {
        "ext": "mp4",
        "format_id": "mp4",
        "filesize_approx": 12345,
        "formats": [
            {"format_id": "mp4", "ext": "mp4", "url": "http://example.com/a.mp4", "vcodec": None},
        ],
    }
    formats = build_formats(info)
    assert [f.format_id for f in formats] == ["mp4", "mp3"]
    original = formats[0]
    assert original.type == "video"
    assert original.ext == "mp4"
    assert original.filesize == 12345
    assert original.requires_merge is False
    assert formats[1].type == "audio"
    assert formats[1].ext == "mp3"


def test_direct_audio_file_exposes_original_audio():
    info = {
        "ext": "mp3",
        "format_id": "mp3",
        "formats": [],
    }
    formats = build_formats(info)
    assert formats[0].type == "audio"
    assert formats[0].ext == "mp3"
    assert formats[0].label.startswith("Original audio")


def test_direct_file_without_formats_key():
    info = {"ext": "webm", "format_id": "0"}
    formats = build_formats(info)
    assert formats[0].type == "video"
    assert formats[0].ext == "webm"
    assert formats[-1].format_id == "mp3"


def test_real_multi_format_extraction_unchanged():
    info = {
        "formats": [
            {
                "format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none",
                "height": 1080, "fps": 30, "tbr": 4000,
            },
            {
                "format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a.40.2",
                "height": 360, "fps": 30, "tbr": 600,
            },
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128},
        ],
    }
    formats = build_formats(info)
    by_id = {f.format_id: f for f in formats}
    assert by_id["137"].requires_merge is True  # video-only stream needs merge
    assert by_id["18"].requires_merge is False  # progressive stream
    assert by_id["140"].type == "audio"
    assert formats[-1].format_id == "mp3"
    # video options are ordered highest resolution first
    assert formats[0].format_id == "137"
