from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("XAI_API_KEY", "")
os.environ.setdefault("XAI_MODEL", "grok-4.5")

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("XAI_API_KEY", "")
    get_settings.cache_clear()
    return TestClient(app)
