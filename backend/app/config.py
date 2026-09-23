"""Application configuration.

All configuration is resolved from environment variables so that the same
code can run locally, inside Docker, and inside the test-suite (where every
test gets an isolated, temporary data directory).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

# Location of the repository root: backend/app/config.py -> backend/app -> backend -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    downloads_dir: Path
    db_path: Path
    ffmpeg_path: str | None
    max_history_items: int = 500
    socket_timeout: int = 20
    extraction_timeout: int = 45
    cors_origins: tuple[str, ...] = ("*",)
    api_key: str | None = None
    allow_private_urls: bool = False
    max_download_bytes: int | None = None
    file_ttl_hours: float | None = None

    @property
    def auth_required(self) -> bool:
        return bool(self.api_key)

    @classmethod
    def create(cls, data_dir: str | Path | None = None) -> Settings:
        base = Path(data_dir) if data_dir is not None else Path(
            os.environ.get("ALLIN1_DATA_DIR", REPO_ROOT / "data")
        )
        base = base.resolve()
        downloads_dir = base / "downloads"
        db_path = base / "history.db"
        base.mkdir(parents=True, exist_ok=True)
        downloads_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_path = shutil.which(os.environ.get("FFMPEG_BINARY", "ffmpeg"))
        return cls(
            data_dir=base,
            downloads_dir=downloads_dir,
            db_path=db_path,
            ffmpeg_path=ffmpeg_path,
            cors_origins=parse_cors_origins(os.environ.get("ALLIN1_CORS_ORIGINS")),
            api_key=parse_api_key(os.environ.get("ALLIN1_API_KEY")),
            allow_private_urls=parse_bool(os.environ.get("ALLIN1_ALLOW_PRIVATE_URLS")),
            max_download_bytes=parse_megabytes(os.environ.get("ALLIN1_MAX_DOWNLOAD_MB")),
            file_ttl_hours=parse_hours(os.environ.get("ALLIN1_FILE_TTL_HOURS")),
        )


def parse_cors_origins(raw: str | None) -> tuple[str, ...]:
    """Turn ``ALLIN1_CORS_ORIGINS`` into a tuple of allowed origins.

    Unset/empty falls back to ``*``. The bundled PWA and the Android shell are
    same-origin and do not need this at all, so the wildcard is only there so
    that ad-hoc web clients keep working; narrow it to your own origin when you
    front the API with other sites. Cross-origin callers still need the API key
    when ``ALLIN1_API_KEY`` is set, so a wildcard here is not a bypass.
    """
    if raw is None or not raw.strip():
        return ("*",)
    origins = tuple(part.strip() for part in raw.split(",") if part.strip())
    return origins or ("*",)


def parse_api_key(raw: str | None) -> str | None:
    """Normalise ``ALLIN1_API_KEY``.

    Unset/blank means "no authentication" (the default, suitable for local use
    only). Reject obviously weak values so a public deployment cannot end up
    with a guessable key.
    """
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    if len(key) < 16:
        raise ValueError(
            "ALLIN1_API_KEY must be at least 16 characters long. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    return key


def parse_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_megabytes(raw: str | None) -> int | None:
    """``ALLIN1_MAX_DOWNLOAD_MB`` -> bytes. 0/unset/blank means unlimited."""
    if raw is None or not raw.strip():
        return None
    try:
        megabytes = int(float(raw.strip()))
    except ValueError:
        return None
    if megabytes <= 0:
        return None
    return megabytes * 1024 * 1024


def parse_hours(raw: str | None) -> float | None:
    """``ALLIN1_FILE_TTL_HOURS`` -> hours. 0/unset/blank means "keep forever"."""
    if raw is None or not raw.strip():
        return None
    try:
        hours = float(raw.strip())
    except ValueError:
        return None
    if hours <= 0:
        return None
    return hours


def ffmpeg_is_available() -> bool:
    return shutil.which(os.environ.get("FFMPEG_BINARY", "ffmpeg")) is not None
