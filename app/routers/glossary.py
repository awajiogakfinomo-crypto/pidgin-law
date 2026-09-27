from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Query

from app.models.schemas import GlossaryLookupResponse, SampleDocument
from app.services.glossary import lookup

router = APIRouter(prefix="/api", tags=["glossary"])
SAMPLES_PATH = Path(__file__).resolve().parent.parent / "data" / "samples.json"


@router.get("/glossary", response_model=GlossaryLookupResponse)
def glossary(
    q: str | None = Query(default=None, description="Search term, alias, or Pidgin phrase"),
    limit: int = Query(default=80, ge=1, le=200),
) -> GlossaryLookupResponse:
    entries = lookup(q, limit=limit)
    return GlossaryLookupResponse(query=q, count=len(entries), entries=entries)


@router.get("/samples", response_model=list[SampleDocument])
def samples() -> list[SampleDocument]:
    with SAMPLES_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return [SampleDocument(**item) for item in data]
