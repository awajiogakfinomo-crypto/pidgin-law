import json

from app.config import Settings
from app.models.schemas import Tone
from app.services.source_ingest import extract_file_text
from app.services.translator import translate_document, translate_gemini_media


def test_upload_text_file_uses_existing_translation(client):
    response = client.post(
        "/api/translate/file",
        files={"file": ("agreement.txt", b"The tenant waives the right.", "text/plain")},
        data={"tone": "everyday", "include_glossary": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "dictionary"
    assert body["original"] == "The tenant waives the right."
    assert any(item["term"].lower() == "waiver" for item in body["glossary"])


def test_audio_upload_requires_gemini_key(client):
    response = client.post(
        "/api/translate/file",
        files={"file": ("recording.mp3", b"fake-audio", "audio/mpeg")},
    )
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_url_translation_blocks_local_network(client):
    response = client.post(
        "/api/translate/url",
        json={"url": "http://127.0.0.1/private.pdf"},
    )
    assert response.status_code == 400
    assert "local-network" in response.json()["detail"]


def test_extract_text_file():
    assert extract_file_text("notice.txt", b"  Tenant notice  ") == "Tenant notice"


def test_gemini_text_translation(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "translation": "Di tenant fit leave.",
                "glossary": [],
                "caution": None,
            })}]}}]}

    monkeypatch.setattr("app.services.translator.httpx.post", lambda *args, **kwargs: FakeResponse())
    settings = Settings(gemini_api_key="test-key", gemini_model="gemini-test")
    result = translate_document("Gemini-specific lease clause.", Tone.everyday, settings=settings)
    assert result.mode == "llm"
    assert result.translation == "Di tenant fit leave."


def test_gemini_media_translation(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({
                "transcription": "The tenant shall pay rent.",
                "translation": "Tenant go pay rent.",
                "glossary": [],
                "caution": None,
            })}]}}]}

    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.services.translator.httpx.post", fake_post)
    settings = Settings(gemini_api_key="test-key", gemini_model="gemini-test")
    result = translate_gemini_media(b"audio-bytes", "audio/mpeg", Tone.formal, True, settings, "recording.mp3")
    assert result.original == "The tenant shall pay rent."
    assert result.translation == "Tenant go pay rent."
    assert captured["json"]["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "audio/mpeg"