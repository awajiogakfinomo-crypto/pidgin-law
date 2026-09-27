from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("GROQ_API_KEY", "")

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    return TestClient(app)
