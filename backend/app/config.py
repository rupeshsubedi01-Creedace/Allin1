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
        )


def ffmpeg_is_available() -> bool:
    return shutil.which(os.environ.get("FFMPEG_BINARY", "ffmpeg")) is not None
