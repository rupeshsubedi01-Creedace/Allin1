from __future__ import annotations

from fastapi import APIRouter, Depends

from ..api.deps import get_settings
from ..config import Settings

router = APIRouter()


@router.get("/api/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    """Public probe endpoint (hosting platforms poll it, PWA checks it on load).

    ``auth_required`` tells the web UI whether to ask for an API key before it
    starts making calls. It is intentionally the only thing this endpoint
    reveals beyond liveness.
    """
    return {
        "status": "ok",
        "ffmpeg_available": settings.ffmpeg_path is not None,
        "auth_required": settings.auth_required,
    }
