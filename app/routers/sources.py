from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.models.schemas import Tone, TranslateResponse
from app.routers.translate import limiter
from app.services.rate_limit import SlidingWindowLimiter, client_ip
from app.services.source_ingest import (
    MAX_SOURCE_BYTES,
    extract_file_text,
    fetch_url_source,
    is_audio_filename,
    mime_type_for_audio,
)
from app.services.translator import translate_document, translate_groq_audio

router = APIRouter(prefix="/api/translate", tags=["translate"])


class URLSourceRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    tone: Tone = Tone.everyday
    include_glossary: bool = True


@router.post("/file", response_model=TranslateResponse)
async def translate_file(
    request: Request,
    file: UploadFile = File(...),
    tone: Tone = Form(Tone.everyday),
    include_glossary: bool = Form(True),
    settings: Settings = Depends(get_settings),
    rate: SlidingWindowLimiter = Depends(limiter),
) -> TranslateResponse:
    rate.check(client_ip(request))
    filename = (file.filename or "upload").strip()
    data = await file.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        await file.close()
        raise HTTPException(status_code=413, detail="Files must be 14 MB or smaller.")

    try:
        if is_audio_filename(filename):
            if not settings.groq_configured:
                raise HTTPException(status_code=503, detail="Configure GROQ_API_KEY on the server to translate audio files.")
            return translate_groq_audio(
                data,
                mime_type_for_audio(filename),
                tone,
                include_glossary,
                settings,
                filename,
            )

        text = extract_file_text(filename, data)
        if not text and filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="This PDF has no selectable text. Groq audio translation is supported, but scanned-PDF OCR is not enabled.")
        return translate_document(text, tone, include_glossary, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not translate that file: {exc}") from exc
    finally:
        await file.close()


@router.post("/url", response_model=TranslateResponse)
def translate_url(
    payload: URLSourceRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    rate: SlidingWindowLimiter = Depends(limiter),
) -> TranslateResponse:
    rate.check(client_ip(request))
    try:
        source = fetch_url_source(payload.url)
        if source.media is not None and source.mime_type:
            if source.mime_type == "application/pdf":
                raise HTTPException(status_code=400, detail="Scanned PDF links are not supported. Use a searchable PDF or paste its text.")
            if not settings.groq_configured:
                raise HTTPException(status_code=503, detail="Configure GROQ_API_KEY on the server to translate linked audio files.")
            return translate_groq_audio(
                source.media,
                source.mime_type,
                payload.tone,
                payload.include_glossary,
                settings,
                payload.url,
            )
        if not source.text:
            raise ValueError("No readable content was found at that link.")
        return translate_document(source.text, payload.tone, payload.include_glossary, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not read or translate that link: {exc}") from exc