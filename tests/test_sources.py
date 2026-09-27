import json

from app.config import Settings
from app.models.schemas import Tone
from app.services.source_ingest import extract_file_text
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