from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.models.schemas import GlossaryEntry

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "legal_glossary.json"


@lru_cache
def load_glossary() -> list[dict]:
    with DATA_PATH.open(encoding="utf-8") as handle:
        entries = json.load(handle)
    for item in entries:
        item["term"] = item["term"].strip()
        item["aliases"] = [alias.strip() for alias in item.get("aliases", []) if alias.strip()]
    return entries


def _phrases_for(entry: dict) -> list[str]:
    phrases = [entry["term"], *entry.get("aliases", [])]
    phrases.sort(key=len, reverse=True)
    return phrases


def _compile_pattern(phrase: str) -> re.Pattern[str]:
    # Allow flexible whitespace and optional punctuation between words.
    parts = [re.escape(part) for part in re.split(r"\s+", phrase.strip()) if part]
    body = r"[\s\-./]*".join(parts)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


@lru_cache
def _compiled_index() -> list[tuple[dict, list[tuple[str, re.Pattern[str]]]]]:
    index: list[tuple[dict, list[tuple[str, re.Pattern[str]]]]] = []
    for entry in load_glossary():
        compiled = [(phrase, _compile_pattern(phrase)) for phrase in _phrases_for(entry)]
        index.append((entry, compiled))
    index.sort(key=lambda item: max(len(phrase) for phrase, _ in item[1]), reverse=True)
    return index


def detect_terms(text: str, limit: int = 24) -> list[GlossaryEntry]:
    """Return unique glossary hits, longest phrases first, without overlapping spans."""
    if not text.strip():
        return []

    occupied: list[tuple[int, int]] = []
    found: list[GlossaryEntry] = []
    seen_terms: set[str] = set()

    for entry, phrases in _compiled_index():
        key = entry["term"].lower()
        if key in seen_terms:
            continue
        matched = False
        for _phrase, pattern in phrases:
            for hit in pattern.finditer(text):
                span = hit.span()
                if _overlaps(span, occupied):
                    continue
                occupied.append(span)
                matched = True
                break
            if matched:
                break
        if matched:
            seen_terms.add(key)
            found.append(_to_entry(entry, source="dictionary"))
            if len(found) >= limit:
                break
    return found


def lookup(query: str | None = None, limit: int = 200) -> list[GlossaryEntry]:
    entries = load_glossary()
    if query:
        needle = query.strip().lower()
        entries = [
            item
            for item in entries
            if needle in item["term"].lower()
            or any(needle in alias.lower() for alias in item.get("aliases", []))
            or needle in item["pidgin_term"].lower()
            or needle in item["explanation"].lower()
        ]
    return [_to_entry(item) for item in entries[:limit]]


def merge_glossary(
    dictionary_hits: list[GlossaryEntry],
    model_hits: list[GlossaryEntry],
    limit: int = 20,
) -> list[GlossaryEntry]:
    merged: list[GlossaryEntry] = []
    seen: set[str] = set()
    for item in [*dictionary_hits, *model_hits]:
        key = item.term.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _overlaps(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    start, end = span
    for other_start, other_end in occupied:
        if start < other_end and end > other_start:
            return True
    return False


def _to_entry(raw: dict, source: str = "dictionary") -> GlossaryEntry:
    return GlossaryEntry(
        term=raw["term"],
        pidgin_term=raw["pidgin_term"],
        explanation=raw["explanation"],
        example=raw["example"],
        source=source,  # type: ignore[arg-type]
    )
