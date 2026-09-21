from __future__ import annotations

from fastapi import APIRouter, Depends

from ..api.deps import get_settings
from ..config import Settings
from ..schemas import ExtractRequest, ExtractResponse
from ..services import extractor
from ..services.errors import AppError

router = APIRouter()


@router.post("/api/extract", response_model=ExtractResponse)
def extract(payload: ExtractRequest, settings: Settings = Depends(get_settings)) -> ExtractResponse:
    try:
        return extractor.extract_info(payload.url, settings)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        from ..services.errors import classify_exception

        raise classify_exception(exc) from exc
