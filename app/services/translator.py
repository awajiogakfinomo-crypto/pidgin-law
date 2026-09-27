from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from collections import OrderedDict
from time import perf_counter

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

    if settings.groq_configured:
        try:
            result = _translate_with_groq(text, tone, dictionary_hits, include_glossary, settings)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Groq translation failed; using dictionary fallback")
            failure_detail = " ".join(str(exc).split())
            if len(failure_detail) > 180:
                failure_detail = failure_detail[:177] + "..."
            failure_reason = f": {failure_detail}" if failure_detail else ""
            result = _dictionary_fallback(
                text,
                tone,
                dictionary_hits,
                caution=(
                    "Full Pidgin translation no succeed this time "
                    f"({exc.__class__.__name__}{failure_reason}). We show dictionary explanations instead."
                ),
            )
    else:
        result = _dictionary_fallback(
            text,
            tone,
            dictionary_hits,
            caution=None,
        )

    if result.mode == "llm" or not settings.groq_configured:
        _cache.set(cache_key, result)
    return result


def _translate_with_groq(
    text: str,
    tone: Tone,
    dictionary_hits: list[GlossaryEntry],
    include_glossary: bool,
    settings: Settings,
) -> TranslateResponse:
    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
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


def translate_groq_audio(
    media: bytes,
    mime_type: str,
    tone: Tone,
    include_glossary: bool,
    settings: Settings,
    source_label: str,
) -> TranslateResponse:
    if not settings.groq_configured:
        raise ValueError("Set GROQ_API_KEY on the server to translate audio files.")

    client = OpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        timeout=settings.request_timeout,
    )
    transcription = client.audio.transcriptions.create(
        model=settings.groq_audio_model,
        file=(source_label, media, mime_type),
        response_format="text",
    )
    source_text = str(getattr(transcription, "text", transcription)).strip()
    if not source_text:
        raise TranslationError("Groq returned an empty audio transcription.")
    return translate_document(source_text, tone, include_glossary, settings)


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
                    model=settings.groq_model,
                    messages=messages,
                    temperature=0.25,
                    response_format={"type": "json_object"},
                )
            except Exception:
                # Some models reject response_format; retry without it once per attempt.
                response = client.chat.completions.create(
                    model=settings.groq_model,
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

        # Retry through the compatible responses endpoint when available.
        try:
            joined = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
            response = client.responses.create(
                model=settings.groq_model,
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
