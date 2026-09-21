"""Lightweight, dependency-free platform detection and URL validation.

This mirrors the logic used on the frontend for instant feedback, and is
also used server-side as the authoritative check before any network call is
made.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


@dataclass(frozen=True)
class Platform:
    key: str
    label: str
    icon: str


_GENERIC = Platform(key="generic", label="Direct / Other", icon="🔗")

_PLATFORMS: list[tuple[re.Pattern, Platform]] = [
    (re.compile(r"(^|\.)youtube\.com$|^youtu\.be$", re.I), Platform("youtube", "YouTube", "▶️")),
    (re.compile(r"(^|\.)tiktok\.com$", re.I), Platform("tiktok", "TikTok", "🎵")),
    (re.compile(r"(^|\.)instagram\.com$", re.I), Platform("instagram", "Instagram", "📸")),
    (re.compile(r"(^|\.)(twitter\.com|x\.com)$", re.I), Platform("twitter", "Twitter / X", "🐦")),
    (re.compile(r"(^|\.)(facebook\.com|fb\.watch)$", re.I), Platform("facebook", "Facebook", "📘")),
    (re.compile(r"(^|\.)(t\.me|telegram\.org|telegram\.me)$", re.I), Platform("telegram", "Telegram", "✈️")),
    (re.compile(r"(^|\.)vimeo\.com$", re.I), Platform("vimeo", "Vimeo", "🎬")),
    (re.compile(r"(^|\.)reddit\.com$", re.I), Platform("reddit", "Reddit", "👽")),
    (re.compile(r"(^|\.)soundcloud\.com$", re.I), Platform("soundcloud", "SoundCloud", "🎧")),
    (re.compile(r"(^|\.)twitch\.tv$", re.I), Platform("twitch", "Twitch", "🟣")),
    (re.compile(r"(^|\.)dailymotion\.com$", re.I), Platform("dailymotion", "Dailymotion", "🎥")),
]


def is_valid_url(url: str) -> bool:
    if not url or len(url) > 4096:
        return False
    url = url.strip()
    if not _URL_RE.match(url):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def detect_platform(url: str) -> Platform:
    try:
        host = urlparse(url.strip()).hostname or ""
    except ValueError:
        return _GENERIC
    host = host.lower()
    for pattern, platform in _PLATFORMS:
        if pattern.search(host):
            return platform
    return _GENERIC
