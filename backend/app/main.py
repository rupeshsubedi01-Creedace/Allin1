"""FastAPI application factory for Allin1."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import routes_download, routes_extract, routes_health, routes_history
from .config import FRONTEND_DIR, Settings
from .db import HistoryStore
from .services.downloader import DownloadManager
from .services.errors import AppError


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    settings = Settings.create(data_dir=data_dir)
    history_store = HistoryStore(settings.db_path)
    download_manager = DownloadManager(settings=settings, history=history_store)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        history_store.close()

    app = FastAPI(
        title="Allin1",
        description="Universal media downloader API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.history_store = history_store
    app.state.download_manager = download_manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    app.include_router(routes_health.router)
    app.include_router(routes_extract.router)
    app.include_router(routes_download.router)
    app.include_router(routes_history.router)

    if FRONTEND_DIR.exists():
        app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend-assets")

        @app.get("/")
        async def serve_index() -> FileResponse:
            return FileResponse(str(FRONTEND_DIR / "index.html"))

        @app.get("/manifest.json")
        async def serve_manifest() -> FileResponse:
            return FileResponse(str(FRONTEND_DIR / "manifest.json"))

        @app.get("/service-worker.js")
        async def serve_sw() -> FileResponse:
            return FileResponse(str(FRONTEND_DIR / "service-worker.js"), media_type="application/javascript")

    return app


app = create_app()
