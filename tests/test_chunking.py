from app.services.chunking import chunk_text, count_words, pair_paragraphs


def test_count_words():
    assert count_words("  Hello,   world.  ") == 2
    assert count_words("") == 0


def test_chunk_text_keeps_short_docs_whole():
    text = "One paragraph only."
    assert chunk_text(text, max_words=10) == [text]


def test_chunk_text_splits_on_paragraphs():
    paragraphs = [f"Word{i} " * 20 for i in range(8)]
    text = "\n\n".join(p.strip() for p in paragraphs)
    chunks = chunk_text(text, max_words=50)
    assert len(chunks) > 1
    assert all(count_words(chunk) <= 50 for chunk in chunks)
    assert "Word0" in chunks[0]


def test_pair_paragraphs_aligns_when_counts_match():
    english = "First.\n\nSecond."
    pidgin = "Na first.\n\nNa second."
    pairs = pair_paragraphs(english, pidgin)
    assert pairs == [("First.", "Na first."), ("Second.", "Na second.")]


def test_pair_paragraphs_falls_back_when_counts_differ():
    pairs = pair_paragraphs("One.\n\nTwo.", "All for one paragraph.")
    assert len(pairs) == 1
    assert "One." in pairs[0][0]
