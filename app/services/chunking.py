from __future__ import annotations

import re


WORD_RE = re.compile(r"\S+")


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text.strip())) if text and text.strip() else 0


def split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [part.strip() for part in parts if part.strip()]


def chunk_text(text: str, max_words: int = 1400) -> list[str]:
    """Split long documents on paragraph boundaries, keeping each chunk under max_words."""
    total = count_words(text)
    if total <= max_words:
        return [text.strip()]

    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return _hard_split(text, max_words)

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for para in paragraphs:
        para_words = count_words(para)
        if para_words > max_words:
            if current:
                chunks.append("\n\n".join(current))
                current, current_words = [], 0
            chunks.extend(_hard_split(para, max_words))
            continue
        if current and current_words + para_words > max_words:
            chunks.append("\n\n".join(current))
            current, current_words = [para], para_words
        else:
            current.append(para)
            current_words += para_words

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def pair_paragraphs(english: str, pidgin: str) -> list[tuple[str, str]]:
    left = split_paragraphs(english)
    right = split_paragraphs(pidgin)
    if left and right and len(left) == len(right):
        return list(zip(left, right, strict=True))
    return [(english.strip(), pidgin.strip())]


def _hard_split(text: str, max_words: int) -> list[str]:
    words = WORD_RE.findall(text)
    chunks = []
    for index in range(0, len(words), max_words):
        chunks.append(" ".join(words[index : index + max_words]))
    return chunks
