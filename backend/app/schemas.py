"""Pydantic request/response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MediaType = Literal["video", "audio"]
JobStatus = Literal["queued", "downloading", "processing", "completed", "error", "canceled"]


class ExtractRequest(BaseModel):
    url: str = Field(..., min_length=3, max_length=4096)


class FormatOption(BaseModel):
    format_id: str
    type: MediaType
    label: str
    ext: str
    resolution: str | None = None
    fps: float | None = None
    abr: float | None = None
    vcodec: str | None = None
    acodec: str | None = None
    filesize: int | None = None
    requires_merge: bool = False


class ExtractResponse(BaseModel):
    title: str
    webpage_url: str
    thumbnail: str | None = None
    duration: float | None = None
    uploader: str | None = None
    platform_key: str
    platform_label: str
    platform_icon: str
    formats: list[FormatOption]


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=3, max_length=4096)
    format_id: str
    media_type: MediaType
    ext: str = "mp4"
    requires_merge: bool = False
    title: str | None = None
    thumbnail: str | None = None
    platform_key: str | None = "generic"
    platform_label: str | None = "Direct / Other"


class DownloadStartResponse(BaseModel):
    job_id: str


class HistoryItem(BaseModel):
    id: str
    url: str
    title: str | None
    platform_key: str | None
    platform_label: str | None
    thumbnail: str | None
    format_id: str | None
    media_type: str | None
    ext: str | None
    requires_merge: bool = False
    filepath: str | None
    filesize: int | None
    status: str
    error_message: str | None
    created_at: str
    updated_at: str

    @property
    def has_file(self) -> bool:
        return bool(self.filepath)


class ErrorResponse(BaseModel):
    error_code: str
    message: str
