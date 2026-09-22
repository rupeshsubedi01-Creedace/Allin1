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
        )


def parse_cors_origins(raw: str | None) -> tuple[str, ...]:
    """Turn ``ALLIN1_CORS_ORIGINS`` into a tuple of allowed origins.

    Unset/empty falls back to ``*``. The API is public, holds no credentials
    and is consumed by the bundled PWA (same origin) and the Android shell, so
    a wildcard is a safe default; set an explicit comma-separated allowlist if
    you front it with other web clients.
    """
    if raw is None or not raw.strip():
        return ("*",)
    origins = tuple(part.strip() for part in raw.split(",") if part.strip())
    return origins or ("*",)


def ffmpeg_is_available() -> bool:
    return shutil.which(os.environ.get("FFMPEG_BINARY", "ffmpeg")) is not None
