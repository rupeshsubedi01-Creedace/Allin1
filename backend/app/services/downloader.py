"""Manages background download jobs and streams live progress to clients."""

from __future__ import annotations

import json
import queue
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yt_dlp

from ..config import Settings
from ..db import HistoryStore
from . import errors, platform_detect


@dataclass
class Job:
    id: str
    url: str
    format_id: str
    media_type: str
    ext: str
    requires_merge: bool
    title: str | None = None
    status: str = "queued"
    percent: float = 0.0
    speed: float | None = None
    eta: int | None = None
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    filepath: str | None = None
    error: dict[str, str] | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    events: queue.Queue[dict[str, Any]] = field(default_factory=queue.Queue)
    thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "percent": round(self.percent, 1),
            "speed": self.speed,
            "eta": self.eta,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "error": self.error,
        }


class _CancelledSentinel(errors.AppError):
    code = "canceled"
    status_code = 499
    default_message = "Download canceled by user."


class DownloadManager:
    def __init__(self, settings: Settings, history: HistoryStore):
        self.settings = settings
        self.history = history
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Job bookkeeping
    # ------------------------------------------------------------------ #
    def _register(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get_job(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise errors.JobNotFoundError()
        return job

    def cancel(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job.status in ("completed", "error", "canceled"):
            raise errors.JobAlreadyFinishedError()
        job.cancel_event.set()

    # ------------------------------------------------------------------ #
    # Starting downloads
    # ------------------------------------------------------------------ #
    def start_download(
        self,
        *,
        url: str,
        format_id: str,
        media_type: str,
        ext: str,
        requires_merge: bool,
        title: str | None,
        thumbnail: str | None,
        platform_key: str | None,
        platform_label: str | None,
    ) -> str:
        if not platform_detect.is_valid_url(url):
            raise errors.InvalidURLError()

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            url=url,
            format_id=format_id,
            media_type=media_type,
            ext=ext,
            requires_merge=requires_merge,
            title=title,
        )
        self._register(job)

        self.history.create(
            job_id=job_id,
            url=url,
            title=title,
            platform_key=platform_key,
            platform_label=platform_label,
            thumbnail=thumbnail,
            format_id=format_id,
            media_type=media_type,
            ext="mp3" if format_id == "mp3" else ext,
            requires_merge=requires_merge,
            status="queued",
        )

        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        job.thread = thread
        thread.start()
        return job_id

    # ------------------------------------------------------------------ #
    # Worker
    # ------------------------------------------------------------------ #
    def _push(self, job: Job, extra: dict[str, Any] | None = None) -> None:
        payload = job.snapshot()
        if extra:
            payload.update(extra)
        job.events.put(payload)

    def _progress_hook(self, job: Job, d: dict[str, Any]) -> None:
        if job.cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Canceled by user")

        status = d.get("status")
        if status == "downloading":
            job.status = "downloading"
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes") or 0
            job.downloaded_bytes = downloaded
            job.total_bytes = total
            job.percent = (downloaded / total * 100) if total else 0.0
            job.speed = d.get("speed")
            job.eta = d.get("eta")
            self._push(job)
        elif status == "finished":
            job.status = "processing"
            job.percent = 100.0
            self._push(job)

    def _postprocessor_hook(self, job: Job, d: dict[str, Any]) -> None:
        if job.cancel_event.is_set():
            raise yt_dlp.utils.DownloadCancelled("Canceled by user")
        if d.get("status") == "started":
            job.status = "processing"
            self._push(job, {"message": f"Running {d.get('postprocessor', 'post-processing')}..."})
        elif d.get("status") == "finished":
            job.status = "processing"
            self._push(job)

    def _build_ydl_opts(self, job: Job) -> dict[str, Any]:
        outtmpl = str(self.settings.downloads_dir / f"{job.id}.%(ext)s")
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "outtmpl": outtmpl,
            "socket_timeout": self.settings.socket_timeout,
            "geo_bypass": True,
            "progress_hooks": [lambda d: self._progress_hook(job, d)],
            "postprocessor_hooks": [lambda d: self._postprocessor_hook(job, d)],
            "retries": 3,
            "fragment_retries": 3,
        }
        if self.settings.ffmpeg_path:
            opts["ffmpeg_location"] = self.settings.ffmpeg_path

        if job.media_type == "audio":
            opts["format"] = "bestaudio/best"
            if job.format_id == "mp3":
                opts["postprocessors"] = [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ]
            else:
                opts["format"] = job.format_id
        else:
            if job.requires_merge:
                opts["format"] = f"{job.format_id}+bestaudio/best"
                opts["merge_output_format"] = job.ext or "mp4"
            else:
                opts["format"] = job.format_id

        return opts

    def _locate_output_file(self, job: Job) -> Path | None:
        matches = sorted(self.settings.downloads_dir.glob(f"{job.id}.*"))
        return matches[0] if matches else None

    def _run(self, job: Job) -> None:
        job.status = "downloading"
        self.history.update(job.id, status="downloading")
        self._push(job)

        opts = self._build_ydl_opts(job)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([job.url])
        except yt_dlp.utils.DownloadCancelled:
            job.status = "canceled"
            job.error = _CancelledSentinel().to_dict()
            self.history.update(job.id, status="canceled")
            self._push(job)
            self._cleanup_partial(job)
            return
        except Exception as exc:  # noqa: BLE001
            app_error = errors.classify_exception(exc)
            job.status = "error"
            job.error = app_error.to_dict()
            self.history.update(job.id, status="error", error_message=app_error.message)
            self._push(job)
            self._cleanup_partial(job)
            return

        output_file = self._locate_output_file(job)
        if output_file is None or not output_file.exists():
            app_error = errors.ExtractionError("Download finished but the output file could not be found.")
            job.status = "error"
            job.error = app_error.to_dict()
            self.history.update(job.id, status="error", error_message=app_error.message)
            self._push(job)
            return

        filesize = output_file.stat().st_size
        job.status = "completed"
        job.percent = 100.0
        job.filepath = str(output_file)
        self.history.update(
            job.id,
            status="completed",
            filepath=str(output_file),
            filesize=filesize,
            ext=output_file.suffix.lstrip("."),
        )
        self._push(job, {"filepath": str(output_file), "filesize": filesize})
        job.events.put({"job_id": job.id, "status": "done"})

    def _cleanup_partial(self, job: Job) -> None:
        for leftover in self.settings.downloads_dir.glob(f"{job.id}*"):
            try:
                leftover.unlink()
            except OSError:
                pass
        job.events.put({"job_id": job.id, "status": "done"})

    # ------------------------------------------------------------------ #
    # SSE stream
    # ------------------------------------------------------------------ #
    def stream_events(self, job_id: str):
        job = self.get_job(job_id)
        # Replay current state immediately so late subscribers aren't stuck.
        yield _sse_format(job.snapshot())
        if job.status in ("completed", "error", "canceled"):
            return
        while True:
            try:
                payload = job.events.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if payload.get("status") == "done":
                return
            yield _sse_format(payload)
            if payload.get("status") in ("completed", "error", "canceled"):
                return


def _sse_format(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"
