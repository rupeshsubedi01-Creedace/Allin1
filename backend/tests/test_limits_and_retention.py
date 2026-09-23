"""Tests for the download size cap and file retention/cleanup."""

from __future__ import annotations

import os
import time
from pathlib import Path

from backend.app.config import Settings
from backend.app.db import HistoryStore
from backend.app.services import extractor
from backend.app.services.downloader import DownloadManager
from backend.app.services.retention import EXPIRED_MESSAGE, purge_expired


def _settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        data_dir=tmp_path / "data",
        downloads_dir=tmp_path / "data" / "downloads",
        db_path=tmp_path / "data" / "history.db",
        ffmpeg_path=None,
        allow_private_urls=True,  # the sample media server runs on 127.0.0.1
    )
    base.update(overrides)
    settings = Settings(**base)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    return settings


def _wait_for_terminal(job):
    deadline = time.time() + 60
    while job.status not in ("completed", "error", "canceled") and time.time() < deadline:
        time.sleep(0.05)
    return job


# ------------------------------------------------------------------ size cap


def test_max_filesize_option_is_only_set_when_configured(tmp_path):
    manager = DownloadManager(_settings(tmp_path), HistoryStore(tmp_path / "h.db"))
    try:
        unlimited = manager._build_ydl_opts(_job_stub(manager))
        assert "max_filesize" not in unlimited
    finally:
        manager.history.close()

    manager = DownloadManager(
        _settings(tmp_path, max_download_bytes=1024), HistoryStore(tmp_path / "h2.db")
    )
    try:
        assert manager._build_ydl_opts(_job_stub(manager))["max_filesize"] == 1024
    finally:
        manager.history.close()


def _job_stub(manager: DownloadManager):
    from backend.app.services.downloader import Job

    return Job(
        id="stub",
        url="https://example.com/v.mp4",
        format_id="best",
        media_type="video",
        ext="mp4",
        requires_merge=False,
    )


def test_oversized_download_is_refused_and_cleaned_up(tmp_path, media_server):
    settings = _settings(tmp_path, max_download_bytes=1024)  # sample video is ~30 KB
    history = HistoryStore(settings.db_path)
    manager = DownloadManager(settings, history)
    try:
        info = extractor.extract_info(media_server, settings)
        chosen = info.formats[0]

        job_id = manager.start_download(
            url=info.webpage_url,
            format_id=chosen.format_id,
            media_type=chosen.type,
            ext=chosen.ext,
            requires_merge=chosen.requires_merge,
            title=info.title,
            thumbnail=None,
            platform_key=info.platform_key,
            platform_label=info.platform_label,
        )
        job = _wait_for_terminal(manager.get_job(job_id))

        assert job.status == "error"
        assert job.error is not None
        assert job.error["error_code"] == "file_too_large"
        assert list(settings.downloads_dir.glob("*")) == [], "partial file should be removed"
        assert history.get(job_id)["status"] == "error"
    finally:
        history.close()


def test_normal_sized_download_still_completes(tmp_path, media_server):
    settings = _settings(tmp_path, max_download_bytes=50 * 1024 * 1024)
    history = HistoryStore(settings.db_path)
    manager = DownloadManager(settings, history)
    try:
        info = extractor.extract_info(media_server, settings)
        audio_format = next(f for f in info.formats if f.type == "audio")
        job_id = manager.start_download(
            url=info.webpage_url,
            format_id=audio_format.format_id,
            media_type="audio",
            ext=audio_format.ext,
            requires_merge=False,
            title=info.title,
            thumbnail=None,
            platform_key=info.platform_key,
            platform_label=info.platform_label,
        )
        job = _wait_for_terminal(manager.get_job(job_id))
        assert job.status == "completed", job.error
    finally:
        history.close()


# ------------------------------------------------------------------ retention


def _seed_history(history: HistoryStore, item_id: str, filepath: Path) -> None:
    history.create(
        job_id=item_id,
        url="https://example.com/video",
        title="Old download",
        platform_key="generic",
        platform_label="Direct",
        thumbnail=None,
        format_id="mp4",
        media_type="video",
        ext="mp4",
        status="completed",
    )
    history.update(item_id, filepath=str(filepath), filesize=filepath.stat().st_size)


def test_purge_expired_deletes_old_files_only(tmp_path):
    settings = _settings(tmp_path, file_ttl_hours=1)
    history = HistoryStore(settings.db_path)
    try:
        old_file = settings.downloads_dir / "old.mp4"
        new_file = settings.downloads_dir / "new.mp4"
        old_file.write_bytes(b"x" * 32)
        new_file.write_bytes(b"y" * 32)
        two_hours_ago = time.time() - 2 * 3600
        os.utime(old_file, (two_hours_ago, two_hours_ago))

        _seed_history(history, "old-job", old_file)
        _seed_history(history, "new-job", new_file)

        removed = purge_expired(settings, history)

        assert removed == 1
        assert not old_file.exists()
        assert new_file.exists()

        old_row = history.get("old-job")
        assert old_row["filepath"] is None
        assert old_row["error_message"] == EXPIRED_MESSAGE
        assert old_row["title"] == "Old download", "metadata must survive cleanup"
        assert history.get("new-job")["filepath"] == str(new_file)
    finally:
        history.close()


def test_purge_is_disabled_without_a_ttl(tmp_path):
    settings = _settings(tmp_path)  # file_ttl_hours unset -> keep files forever
    history = HistoryStore(settings.db_path)
    try:
        keep = settings.downloads_dir / "keep.mp4"
        keep.write_bytes(b"z" * 16)
        ancient = time.time() - 365 * 24 * 3600
        os.utime(keep, (ancient, ancient))
        _seed_history(history, "ancient-job", keep)

        assert purge_expired(settings, history) == 0
        assert keep.exists()
        assert history.get("ancient-job")["filepath"] == str(keep)
    finally:
        history.close()


def test_purge_forgets_missing_files_and_sweeps_orphans(tmp_path):
    settings = _settings(tmp_path, file_ttl_hours=1)
    history = HistoryStore(settings.db_path)
    try:
        vanished = settings.downloads_dir / "vanished.mp4"
        vanished.write_bytes(b"v")
        _seed_history(history, "gone-job", vanished)
        vanished.unlink()  # e.g. the volume was wiped by a redeploy

        orphan = settings.downloads_dir / "orphan.mp4"
        orphan.write_bytes(b"o" * 8)
        stale = time.time() - 5 * 3600
        os.utime(orphan, (stale, stale))

        purge_expired(settings, history)

        assert history.get("gone-job")["filepath"] is None
        assert not orphan.exists()
    finally:
        history.close()
