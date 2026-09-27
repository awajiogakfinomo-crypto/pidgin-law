import json

import httpx

from app.config import Settings
from app.models.schemas import Tone
from app.services.source_ingest import SourceContent, extract_file_text
from app.services.translator import translate_document, translate_groq_audio


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


def test_audio_upload_requires_groq_key(client):
    response = client.post(
        "/api/translate/file",
        files={"file": ("recording.mp3", b"fake-audio", "audio/mpeg")},
    )
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_url_translation_blocks_local_network(client):
    response = client.post(
        "/api/translate/url",
        json={"url": "http://127.0.0.1/private.pdf"},
    )
    assert response.status_code == 400
    assert "local-network" in response.json()["detail"]


def test_url_translation_extracts_searchable_pdf(client, monkeypatch):
    monkeypatch.setattr("app.routers.sources.fetch_url_source", lambda url, user_agent: SourceContent(media=b"pdf", mime_type="application/pdf"))
    monkeypatch.setattr("app.routers.sources.extract_file_text", lambda filename, data: "The court dismissed the appeal.")

    response = client.post("/api/translate/url", json={"url": "https://example.com/case.pdf"})

    assert response.status_code == 200
    assert response.json()["original"] == "The court dismissed the appeal."


def test_url_translation_explains_forbidden_source(client, monkeypatch):
    request = httpx.Request("GET", "https://www.sec.gov/example.pdf")
    response = httpx.Response(403, request=request)
    error = httpx.HTTPStatusError("Forbidden", request=request, response=response)
    monkeypatch.setattr("app.routers.sources.fetch_url_source", lambda url, user_agent: (_ for _ in ()).throw(error))

    result = client.post("/api/translate/url", json={"url": "https://www.sec.gov/example.pdf"})

    assert result.status_code == 502
    assert "SOURCE_USER_AGENT" in result.json()["detail"]
    assert "upload it directly" in result.json()["detail"]


def test_extract_text_file():
    assert extract_file_text("notice.txt", b"  Tenant notice  ") == "Tenant notice"


def test_groq_text_translation(monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            class Message:
                content = json.dumps({"translation": "Di tenant fit leave.", "glossary": [], "caution": None})

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr("app.services.translator.OpenAI", lambda **kwargs: FakeClient())
    settings = Settings(groq_api_key="test-key", groq_model="llama-test")
    result = translate_document("Groq-specific lease clause.", Tone.everyday, settings=settings)
    assert result.mode == "llm"
    assert result.translation == "Di tenant fit leave."


def test_failed_groq_translation_is_not_cached(monkeypatch):
    attempts = 0

    def fail_translation(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("Provider returned HTTP 429")

    monkeypatch.setattr("app.services.translator._translate_with_groq", fail_translation)
    settings = Settings(groq_api_key="test-key", groq_model="retry-test-model")

    first = translate_document("Unique retry test legal text.", Tone.everyday, settings=settings)
    second = translate_document("Unique retry test legal text.", Tone.everyday, settings=settings)

    assert first.mode == "dictionary"
    assert "HTTP 429" in first.caution
    assert second.mode == "dictionary"
    assert attempts == 2


def test_groq_audio_transcription(monkeypatch):
    class FakeAudio:
        class transcriptions:
            @staticmethod
            def create(**kwargs):
                return "The tenant shall pay rent."

    class FakeClient:
        audio = FakeAudio()
        chat = type("FakeChat", (), {
            "completions": type("FakeCompletions", (), {
                "create": staticmethod(lambda **kwargs: type("Response", (), {
                    "choices": [type("Choice", (), {
                        "message": type("Message", (), {
                            "content": json.dumps({"translation": "Tenant go pay rent.", "glossary": [], "caution": None})
                        })()
                    })()]
                })())
            })()
        })()

    monkeypatch.setattr("app.services.translator.OpenAI", lambda **kwargs: FakeClient())
    settings = Settings(groq_api_key="test-key", groq_audio_model="whisper-test")
    result = translate_groq_audio(b"audio-bytes", "audio/mpeg", Tone.formal, True, settings, "recording.mp3")
    assert result.original == "The tenant shall pay rent."
    assert result.mode == "llm"