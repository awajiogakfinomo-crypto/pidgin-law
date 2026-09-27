from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import threading
from collections import OrderedDict
from time import perf_counter

import httpx
from openai import OpenAI

from app.config import Settings, get_settings
from app.models.schemas import (
    GlossaryEntry,
    ParagraphPair,
    Tone,
    TranslateResponse,
)
from app.services.chunking import chunk_text, count_words, pair_paragraphs
from app.services.glossary import detect_terms, merge_glossary
from app.services.prompts import DISCLAIMER, SYSTEM_PROMPT, chunk_user_prompt, user_prompt

logger = logging.getLogger("pidgin_law")

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class TranslationError(Exception):
    """Raised when the model cannot produce a usable translation."""


class _LRUCache:
    def __init__(self, maxsize: int = 48) -> None:
        self.maxsize = maxsize
        self._data: OrderedDict[str, TranslateResponse] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> TranslateResponse | None:
        with self._lock:
            value = self._data.get(key)
            if value is not None:
                self._data.move_to_end(key)
            return value

    def set(self, key: str, value: TranslateResponse) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)


_cache = _LRUCache()


def translate_document(
    text: str,
    tone: Tone = Tone.everyday,
    include_glossary: bool = True,
    settings: Settings | None = None,
) -> TranslateResponse:
    settings = settings or get_settings()

    cache_key = _cache_key(text, tone, include_glossary, settings.active_model)
    cached = _cache.get(cache_key)
    if cached:
        return cached

    dictionary_hits = detect_terms(text) if include_glossary else []

    if settings.gemini_configured:
        try:
            result = _translate_with_gemini(text, tone, dictionary_hits, include_glossary, settings)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gemini translation failed; using dictionary fallback")
            result = _dictionary_fallback(
                text,
                tone,
                dictionary_hits,
                caution=(
                    "Full Pidgin translation no succeed this time "
                    f"({exc.__class__.__name__}). We show dictionary explanations instead."
                ),
            )
    elif settings.xai_api_key and settings.xai_api_key.strip():
        try:
            result = _translate_with_llm(text, tone, dictionary_hits, include_glossary, settings)
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM translation failed; using dictionary fallback")
            result = _dictionary_fallback(
                text,
                tone,
                dictionary_hits,
                caution=(
                    "Full Pidgin translation no succeed this time "
                    f"({exc.__class__.__name__}). We show dictionary explanations "
                    "so you still fit follow di important legal terms. Try again shortly."
                ),
            )
    else:
        result = _dictionary_fallback(
            text,
            tone,
            dictionary_hits,
            caution=None,
        )

    _cache.set(cache_key, result)
    return result


def _translate_with_gemini(
    text: str,
    tone: Tone,
    dictionary_hits: list[GlossaryEntry],
    include_glossary: bool,
    settings: Settings,
) -> TranslateResponse:
    chunks = chunk_text(text, max_words=settings.chunk_words)
    translations: list[str] = []
    model_glossary: list[GlossaryEntry] = []
    cautions: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        prompt = (
            user_prompt(chunk, tone, dictionary_hits)
            if len(chunks) == 1
            else chunk_user_prompt(chunk, tone, dictionary_hits, index, len(chunks))
        )
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.25,
                    "responseMimeType": "application/json",
                },
            },
            timeout=settings.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        candidates = payload.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        raw = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        if not raw.strip():
            raise TranslationError("Gemini returned an empty response.")
        result = _extract_json(raw)
        translation = str(result.get("translation") or "").strip()
        if not translation:
            raise TranslationError("Gemini JSON is missing a translation field.")
        translations.append(translation)
        model_glossary.extend(_parse_model_glossary(result.get("glossary") or []))
        if result.get("caution"):
            cautions.append(str(result["caution"]).strip())

    full_translation = "\n\n".join(translations)
    glossary = merge_glossary(dictionary_hits, model_glossary) if include_glossary else []
    pairs = pair_paragraphs(text, full_translation)
    return TranslateResponse(
        original=text,
        translation=full_translation,
        tone=tone,
        glossary=glossary,
        paragraphs=[ParagraphPair(english=en, pidgin=pid) for en, pid in pairs],
        word_count=count_words(text),
        mode="llm",
        caution=" ".join(cautions) or None,
        disclaimer=DISCLAIMER,
    )


def translate_gemini_media(
    media: bytes,
    mime_type: str,
    tone: Tone,
    include_glossary: bool,
    settings: Settings,
    source_label: str,
) -> TranslateResponse:
    if not settings.gemini_configured:
        raise ValueError("Set GEMINI_API_KEY on the server to translate audio or scanned PDF files.")

    dictionary_hits: list[GlossaryEntry] = []
    prompt = (
        f"Tone: {tone.value.upper()} Nigerian Pidgin.\n\n"
        "The attached source is an audio recording or PDF document containing legal content. "
        "Read or transcribe all legible English legal content, then translate it into Nigerian Pidgin. "
        "For audio, transcribe speech faithfully before translating; omit non-legal conversation only "
        "if it is clearly unrelated. Preserve names, dates, amounts, paragraph/section structure, "
        "and every legal condition. Follow all rules in the system instruction. "
        "Return JSON with transcription (the source text you could read/hear), translation, "
        "glossary, and caution.\n\n"
        f"Source file: {source_label}"
    )
    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
        headers={"x-goog-api-key": settings.gemini_api_key},
        json={
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT + "\nFor this media request, also return a transcription field containing the source words you could read or hear."}]},
            "contents": [{"role": "user", "parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(media).decode("ascii")}},
            ]}],
            "generationConfig": {"temperature": 0.25, "responseMimeType": "application/json"},
        },
        timeout=settings.request_timeout,
    )
    response.raise_for_status()
    candidates = response.json().get("candidates") or []
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    raw = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    if not raw.strip():
        raise TranslationError("Gemini returned an empty response for this file.")
    payload = _extract_json(raw)
    translation = str(payload.get("translation") or "").strip()
    if not translation:
        raise TranslationError("Gemini JSON is missing a translation field.")

    glossary = _parse_model_glossary(payload.get("glossary") or []) if include_glossary else []
    source_text = str(payload.get("transcription") or payload.get("source_text") or source_label).strip()
    return TranslateResponse(
        original=source_text,
        translation=translation,
        tone=tone,
        glossary=glossary,
        paragraphs=[ParagraphPair(english=source_text, pidgin=translation)],
        word_count=count_words(source_text),
        mode="llm",
        caution=str(payload["caution"]).strip() if payload.get("caution") else None,
        disclaimer=DISCLAIMER,
    )


def _translate_with_llm(
    text: str,
    tone: Tone,
    dictionary_hits: list[GlossaryEntry],
    include_glossary: bool,
    settings: Settings,
) -> TranslateResponse:
    client = OpenAI(
        api_key=settings.xai_api_key,
        base_url=settings.xai_base_url,
        timeout=settings.request_timeout,
    )
    chunks = chunk_text(text, max_words=settings.chunk_words)
    translations: list[str] = []
    model_glossary: list[GlossaryEntry] = []
    cautions: list[str] = []
    started = perf_counter()

    for index, chunk in enumerate(chunks, start=1):
        prompt = (
            user_prompt(chunk, tone, dictionary_hits)
            if len(chunks) == 1
            else chunk_user_prompt(chunk, tone, dictionary_hits, index, len(chunks))
        )
        payload = _complete_json(client, prompt, settings)
        translation = (payload.get("translation") or "").strip()
        if not translation:
            raise TranslationError("Model returned an empty translation.")
        translations.append(translation)
        model_glossary.extend(_parse_model_glossary(payload.get("glossary") or []))
        caution = payload.get("caution")
        if caution:
            cautions.append(str(caution).strip())

    elapsed = perf_counter() - started
    logger.info("Translated %s word(s) in %.1fs using %s chunk(s)", count_words(text), elapsed, len(chunks))

    full_translation = "\n\n".join(translations)
    glossary = merge_glossary(dictionary_hits, model_glossary) if include_glossary else []
    pairs = pair_paragraphs(text, full_translation)
    caution = " ".join(cautions) if cautions else None

    return TranslateResponse(
        original=text,
        translation=full_translation,
        tone=tone,
        glossary=glossary,
        paragraphs=[ParagraphPair(english=en, pidgin=pid) for en, pid in pairs],
        word_count=count_words(text),
        mode="llm",
        caution=caution,
        disclaimer=DISCLAIMER,
    )


def _complete_json(client: OpenAI, prompt: str, settings: Settings) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    content = _chat_complete(client, messages, settings)
    parsed = _extract_json(content)
    if "translation" not in parsed:
        raise TranslationError("Model JSON is missing a translation field.")
    return parsed


def _chat_complete(client: OpenAI, messages: list[dict], settings: Settings) -> str:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            try:
                response = client.chat.completions.create(
                    model=settings.xai_model,
                    messages=messages,
                    temperature=0.25,
                    response_format={"type": "json_object"},
                )
            except Exception:
                # Some models reject response_format; retry without it once per attempt.
                response = client.chat.completions.create(
                    model=settings.xai_model,
                    messages=messages,
                    temperature=0.25,
                )
            content = response.choices[0].message.content or ""
            if content.strip():
                return content
            last_error = TranslationError("Empty model response.")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Chat completion attempt %s failed: %s", attempt + 1, exc)

        # Fallback to the Responses API (SpaceXAI / xAI recommended path).
        try:
            joined = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
            response = client.responses.create(
                model=settings.xai_model,
                input=joined,
                temperature=0.25,
            )
            content = getattr(response, "output_text", None) or ""
            if not content:
                content = _collect_response_text(response)
            if content.strip():
                return content
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Responses API attempt %s failed: %s", attempt + 1, exc)

    raise TranslationError(str(last_error) if last_error else "Translation failed.")


def _collect_response_text(response: object) -> str:
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for piece in getattr(item, "content", []) or []:
            text = getattr(piece, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _extract_json(raw: str) -> dict:
    text = _JSON_FENCE.sub("", raw.strip()).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise TranslationError("Could not parse JSON from the model response.")


def _parse_model_glossary(items: object) -> list[GlossaryEntry]:
    if not isinstance(items, list):
        return []
    entries: list[GlossaryEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        if not term:
            continue
        entries.append(
            GlossaryEntry(
                term=term,
                pidgin_term=str(item.get("pidgin_term") or item.get("pidgin") or "").strip()
                or term,
                explanation=str(item.get("explanation") or "").strip(),
                example=str(item.get("example") or "").strip(),
                source="model",
            )
        )
    return entries


def _dictionary_fallback(
    text: str,
    tone: Tone,
    dictionary_hits: list[GlossaryEntry],
    caution: str | None,
) -> TranslateResponse:
    annotated = text
    # Annotate longest terms first so we do not nest replacements badly.
    for entry in sorted(dictionary_hits, key=lambda item: len(item.term), reverse=True):
        pattern = re.compile(rf"(?<![A-Za-z0-9])({re.escape(entry.term)})(?![A-Za-z0-9])", re.IGNORECASE)
        replacement = rf"\1 ({entry.pidgin_term})"
        annotated, _count = pattern.subn(replacement, annotated, count=1)

    heading = (
        "DICTIONARY MODE — important legal terms get Pidgin explanation for bracket. "
        "Di rest of di English remain, so meaning no go spoil.\n\n"
    )
    translation = heading + annotated
    pairs = pair_paragraphs(text, translation)
    return TranslateResponse(
        original=text,
        translation=translation,
        tone=tone,
        glossary=dictionary_hits,
        paragraphs=[ParagraphPair(english=en, pidgin=pid) for en, pid in pairs],
        word_count=count_words(text),
        mode="dictionary",
        caution=caution,
        disclaimer=DISCLAIMER,
    )


def _cache_key(text: str, tone: Tone, include_glossary: bool, model: str) -> str:
    digest = hashlib.sha256(
        f"{tone.value}|{include_glossary}|{model}|{text}".encode("utf-8")
    ).hexdigest()
    return digest
