from __future__ import annotations

from fastapi import APIRouter, Depends

from ..api.deps import get_settings
from ..config import Settings

router = APIRouter()


@router.get("/api/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "ffmpeg_available": settings.ffmpeg_path is not None,
    }
