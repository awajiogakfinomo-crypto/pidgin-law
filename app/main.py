from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __app_name__, __version__
from app.config import get_settings
from app.models.schemas import HealthResponse
from app.routers import export, glossary, sources, translate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("pidgin_law")

STATIC_DIR = Path(__file__).resolve().parent / "static"
settings = get_settings()

app = FastAPI(
    title=__app_name__,
    version=__version__,
    description=(
        "Access-to-Justice translator: English legal text into clear Nigerian Pidgin. "
        "Not legal advice."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(translate.router)
app.include_router(sources.router)
app.include_router(glossary.router)
app.include_router(export.router)


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app=__app_name__,
        version=__version__,
        llm_ready=settings.llm_configured,
        model=settings.active_model,
        max_words=settings.max_words,
    )


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg")


@app.get("/config.js", include_in_schema=False)
def frontend_config() -> FileResponse:
    return FileResponse(STATIC_DIR / "config.js")
