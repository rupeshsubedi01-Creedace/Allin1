"""Automatic cleanup of old downloads.

On a public deployment every visitor's download lands on the same disk, so
without a TTL the volume fills up and the service dies. When
``ALLIN1_FILE_TTL_HOURS`` is set, downloaded files older than that are deleted
and their history row keeps its metadata (the title, link and format) but loses
its ``filepath``, so "Re-download" still works while ``/file`` returns 404.

Unset/0 disables cleanup entirely: nothing is ever deleted behind your back.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from ..config import Settings
from ..db import HistoryStore

logger = logging.getLogger(__name__)

EXPIRED_MESSAGE = "File expired and was deleted to free disk space. Re-download to get it again."
CHECK_INTERVAL_SECONDS = 15 * 60


def purge_expired(settings: Settings, history: HistoryStore) -> int:
    """Delete files older than the TTL. Returns the number of files removed."""
    ttl = settings.file_ttl_hours
    if not ttl:
        return 0

    cutoff = time.time() - ttl * 3600
    removed = 0

    for row in history.list_all(limit=10_000):
        filepath = row.get("filepath")
        if not filepath:
            continue
        path = Path(filepath)
        try:
            if not path.exists():
                # Already gone (manual cleanup, redeploy without a volume, ...):
                # just forget the pointer so the UI stops offering a 404 link.
                history.update(row["id"], filepath=None, error_message=EXPIRED_MESSAGE)
                continue
            if path.stat().st_mtime >= cutoff:
                continue
            path.unlink()
        except OSError as exc:  # pragma: no cover - defensive
            logger.warning("Could not expire %s: %s", filepath, exc)
            continue
        history.update(row["id"], filepath=None, error_message=EXPIRED_MESSAGE)
        removed += 1

    # Sweep orphaned files in the downloads directory that no history row owns.
    known = {row.get("filepath") for row in history.list_all(limit=10_000)}
    for candidate in settings.downloads_dir.glob("*"):
        if str(candidate) in known or not candidate.is_file():
            continue
        try:
            if candidate.stat().st_mtime < cutoff:
                candidate.unlink()
                removed += 1
        except OSError:  # pragma: no cover - defensive
            continue

    return removed


class RetentionJanitor(threading.Thread):
    """Background thread that runs :func:`purge_expired` on a fixed interval."""

    def __init__(self, settings: Settings, history: HistoryStore):
        super().__init__(name="allin1-retention", daemon=True)
        self.settings = settings
        self.history = history
        self._stop_event = threading.Event()

    def run(self) -> None:
        # Give the app a moment to finish starting up before the first sweep.
        while not self._stop_event.wait(30):
            try:
                removed = purge_expired(self.settings, self.history)
                if removed:
                    logger.info("Retention cleanup removed %d file(s)", removed)
            except Exception:  # noqa: BLE001 - a janitor must never crash the app
                logger.exception("Retention cleanup failed")
            if self._stop_event.wait(CHECK_INTERVAL_SECONDS):
                return

    def stop(self) -> None:
        self._stop_event.set()
