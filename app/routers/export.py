from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

from app.models.schemas import ExportRequest
from app.services.pdf_export import build_pdf
from app.services.prompts import DISCLAIMER

router = APIRouter(prefix="/api/export", tags=["export"])


@router.post("/txt")
def export_txt(payload: ExportRequest) -> PlainTextResponse:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    glossary_lines = []
    for entry in payload.glossary:
        glossary_lines.append(
            f"- {entry.term}: {entry.pidgin_term}\n  {entry.explanation}\n  Example: {entry.example}"
        )
    glossary_block = "\n".join(glossary_lines) if glossary_lines else "(no terms detected)"
    body = (
        f"{payload.title}\n"
        f"Pidgin Law · {stamp} · Tone: {payload.tone.value}\n"
        f"{'=' * 60}\n\n"
        f"DISCLAIMER\n{DISCLAIMER}\n\n"
        f"{'-' * 60}\nORIGINAL ENGLISH\n{'-' * 60}\n\n"
        f"{payload.original.strip()}\n\n"
        f"{'-' * 60}\nPIDGIN TRANSLATION\n{'-' * 60}\n\n"
        f"{payload.translation.strip()}\n\n"
        f"{'-' * 60}\nLEGAL GLOSSARY\n{'-' * 60}\n\n"
        f"{glossary_block}\n"
    )
    filename = _filename(payload.title, "txt")
    return PlainTextResponse(
        content=body,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/pdf")
def export_pdf(payload: ExportRequest) -> Response:
    pdf_bytes = build_pdf(
        original=payload.original,
        translation=payload.translation,
        tone=payload.tone.value,
        glossary=payload.glossary,
        title=payload.title,
    )
    filename = _filename(payload.title, "pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _filename(title: str, ext: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in title).strip("-")
    slug = "-".join(part for part in slug.split("-") if part) or "pidgin-law"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    name = f"{slug}-{stamp}.{ext}"
    return quote(name)
