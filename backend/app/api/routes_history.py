from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from ..api.deps import get_history
from ..db import HistoryStore
from ..schemas import HistoryItem
from ..services.errors import HistoryItemNotFoundError

router = APIRouter()


@router.get("/api/history", response_model=list[HistoryItem])
def list_history(history: HistoryStore = Depends(get_history)) -> list[HistoryItem]:
    return [HistoryItem(**row) for row in history.list_all()]


@router.delete("/api/history/{item_id}")
def delete_history_item(item_id: str, history: HistoryStore = Depends(get_history)) -> dict:
    row = history.delete(item_id)
    if row is None:
        raise HistoryItemNotFoundError()
    filepath = row.get("filepath")
    if filepath and os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass
    return {"status": "deleted", "id": item_id}


@router.delete("/api/history")
def clear_history(history: HistoryStore = Depends(get_history)) -> dict:
    rows = history.delete_all()
    removed = 0
    for row in rows:
        filepath = row.get("filepath")
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
                removed += 1
            except OSError:
                pass
    return {"status": "cleared", "count": len(rows), "files_removed": removed}
