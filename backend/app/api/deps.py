from __future__ import annotations

from fastapi import Request

from ..config import Settings
from ..db import HistoryStore
from ..services.downloader import DownloadManager


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_history(request: Request) -> HistoryStore:
    return request.app.state.history_store


def get_download_manager(request: Request) -> DownloadManager:
    return request.app.state.download_manager
