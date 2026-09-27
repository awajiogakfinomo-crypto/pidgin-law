from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Tone(str, Enum):
    formal = "formal"
    everyday = "everyday"


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    tone: Tone = Tone.everyday
    include_glossary: bool = True

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Paste or type some legal English first.")
        return cleaned


class GlossaryEntry(BaseModel):
    term: str
    pidgin_term: str
    explanation: str
    example: str
    source: Literal["dictionary", "model"] = "dictionary"


class ParagraphPair(BaseModel):
    english: str
    pidgin: str


class TranslateResponse(BaseModel):
    original: str
    translation: str
    tone: Tone
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    paragraphs: list[ParagraphPair] = Field(default_factory=list)
    word_count: int
    mode: Literal["llm", "dictionary"]
    caution: str | None = None
    disclaimer: str


class ExportRequest(BaseModel):
    original: str = Field(..., min_length=1)
    translation: str = Field(..., min_length=1)
    tone: Tone = Tone.everyday
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    title: str = "Pidgin Law translation"


class GlossaryLookupResponse(BaseModel):
    query: str | None = None
    count: int
    entries: list[GlossaryEntry]


class SampleDocument(BaseModel):
    id: str
    title: str
    category: str
    description: str
    text: str


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    llm_ready: bool
    model: str
    max_words: int
