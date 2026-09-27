from app.services.translator import translate_document
from app.models.schemas import Tone


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "Pidgin Law"
    assert body["max_words"] >= 1000


def test_samples(client):
    response = client.get("/api/samples")
    assert response.status_code == 200
    samples = response.json()
    assert len(samples) >= 4
    assert {"id", "title", "text", "category"} <= samples[0].keys()
    assert "tenant" in samples[0]["text"].lower() or "Tenant" in samples[0]["text"]


def test_glossary_search(client):
    response = client.get("/api/glossary", params={"q": "indemnify"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    assert any(item["term"].lower() == "indemnify" for item in body["entries"])


def test_homepage_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Pidgin Law" in response.text
    assert "Translate to Pidgin" in response.text


def test_translate_dictionary_fallback(client):
    payload = {
        "text": (
            "The Employee shall indemnify the Company. "
            "Any dispute shall be subject to the jurisdiction of Lagos courts. "
            "The Employee hereby grants a waiver of claims arising from late payment."
        ),
        "tone": "everyday",
        "include_glossary": True,
    }
    response = client.post("/api/translate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "dictionary"
    assert body["translation"]
    assert body["disclaimer"]
    terms = {item["term"].lower() for item in body["glossary"]}
    assert "indemnify" in terms
    assert "jurisdiction" in terms
    assert "waiver" in terms


def test_translate_rejects_empty(client):
    response = client.post("/api/translate", json={"text": "   "})
    assert response.status_code == 422


def test_translate_document_helper_without_llm():
    result = translate_document(
        "This lease includes a quiet enjoyment covenant and a lien on fixtures.",
        tone=Tone.formal,
    )
    assert result.mode == "dictionary"
    terms = {item.term.lower() for item in result.glossary}
    assert "quiet enjoyment" in terms
    assert "lien" in terms
