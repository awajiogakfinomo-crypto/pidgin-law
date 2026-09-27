from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.models.schemas import TranslateRequest, TranslateResponse
from app.services.rate_limit import SlidingWindowLimiter, client_ip
from app.services.translator import translate_document

router = APIRouter(prefix="/api", tags=["translate"])
_limiter: SlidingWindowLimiter | None = None


def limiter(settings: Settings = Depends(get_settings)) -> SlidingWindowLimiter:
    global _limiter
    if _limiter is None:
        _limiter = SlidingWindowLimiter(max_requests=settings.rate_limit_per_minute)
    return _limiter


@router.post("/translate", response_model=TranslateResponse)
def translate(
    payload: TranslateRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    rate: SlidingWindowLimiter = Depends(limiter),
) -> TranslateResponse:
    rate.check(client_ip(request))
    try:
        return translate_document(
            text=payload.text,
            tone=payload.tone,
            include_glossary=payload.include_glossary,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Translation no work: {exc}",
        ) from exc
