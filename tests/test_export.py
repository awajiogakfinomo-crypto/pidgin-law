from app.models.schemas import ExportRequest, GlossaryEntry, Tone
from app.services.pdf_export import build_pdf


def test_export_txt(client):
    payload = {
        "original": "The Tenant shall pay rent.",
        "translation": "Di tenant go pay rent.",
        "tone": "everyday",
        "glossary": [
            {
                "term": "tenant",
                "pidgin_term": "person wey dey rent",
                "explanation": "Person wey dey stay for another person house and dey pay.",
                "example": "Di tenant pay rent every month.",
                "source": "dictionary",
            }
        ],
        "title": "Tenancy note",
    }
    response = client.post("/api/export/txt", json=payload)
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    text = response.text
    assert "Di tenant go pay rent." in text
    assert "DISCLAIMER" in text
    assert "tenant" in text.lower()


def test_export_pdf(client):
    payload = ExportRequest(
        original="Force majeure shall excuse delay.",
        translation="Force majeure (big wahala wey nobody fit control) go excuse delay.",
        tone=Tone.formal,
        glossary=[
            GlossaryEntry(
                term="force majeure",
                pidgin_term="big wahala wey nobody fit control",
                explanation="Serious event wey nobody fit stop.",
                example="Flood fit be force majeure.",
            )
        ],
        title="Contract excerpt",
    )
    response = client.post("/api/export/pdf", json=payload.model_dump())
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_build_pdf_bytes():
    pdf = build_pdf(
        original="Hello",
        translation="How far",
        tone="everyday",
        glossary=[],
        title="Test",
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 200
