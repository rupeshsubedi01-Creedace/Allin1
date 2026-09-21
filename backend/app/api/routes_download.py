from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, StreamingResponse

from ..api.deps import get_download_manager, get_history
from ..db import HistoryStore
from ..schemas import DownloadRequest, DownloadStartResponse
from ..services.downloader import DownloadManager
from ..services.errors import HistoryItemNotFoundError

router = APIRouter()


@router.post("/api/download", response_model=DownloadStartResponse)
def start_download(
    payload: DownloadRequest,
    manager: DownloadManager = Depends(get_download_manager),
) -> DownloadStartResponse:
    job_id = manager.start_download(
        url=payload.url,
        format_id=payload.format_id,
        media_type=payload.media_type,
        ext=payload.ext,
        requires_merge=payload.requires_merge,
        title=payload.title,
        thumbnail=payload.thumbnail,
        platform_key=payload.platform_key,
        platform_label=payload.platform_label,
    )
    return DownloadStartResponse(job_id=job_id)


@router.get("/api/download/{job_id}/events")
def download_events(job_id: str, manager: DownloadManager = Depends(get_download_manager)):
    return StreamingResponse(
        manager.stream_events(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/download/{job_id}/cancel")
def cancel_download(job_id: str, manager: DownloadManager = Depends(get_download_manager)) -> dict:
    manager.cancel(job_id)
    return {"status": "canceling"}


@router.get("/api/download/{job_id}/file")
def get_file(job_id: str, manager: DownloadManager = Depends(get_download_manager)):
    job = manager.get_job(job_id)
    if job.status != "completed" or not job.filepath or not Path(job.filepath).exists():
        raise HistoryItemNotFoundError("The downloaded file is not available (yet).")
    path = Path(job.filepath)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.post("/api/history/{item_id}/redownload", response_model=DownloadStartResponse)
def redownload(
    item_id: str,
    manager: DownloadManager = Depends(get_download_manager),
    history: HistoryStore = Depends(get_history),
) -> DownloadStartResponse:
    record = history.get(item_id)
    if record is None:
        raise HistoryItemNotFoundError()
    job_id = manager.start_download(
        url=record["url"],
        format_id=record["format_id"] or "mp3",
        media_type=record["media_type"] or "audio",
        ext=record["ext"] or "mp4",
        requires_merge=bool(record.get("requires_merge")),
        title=record["title"],
        thumbnail=record["thumbnail"],
        platform_key=record["platform_key"],
        platform_label=record["platform_label"],
    )
    return DownloadStartResponse(job_id=job_id)
