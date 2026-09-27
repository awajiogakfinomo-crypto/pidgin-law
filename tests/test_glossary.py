from app.services.glossary import detect_terms, lookup


SAMPLE = """
The Tenant shall indemnify the Landlord against all claims. Time is of the essence.
This agreement is subject to the laws of Lagos (jurisdiction of the High Court).
The Vendor shall obtain Governor's Consent and produce a Certificate of Occupancy.
Buyer should note caveat emptor. A force majeure event shall suspend performance.
"""


def test_detects_core_legal_terms():
    hits = detect_terms(SAMPLE)
    terms = {item.term.lower() for item in hits}
    assert "indemnify" in terms
    assert "jurisdiction" in terms
    assert "time is of the essence" in terms
    assert "certificate of occupancy" in terms
    assert "governor's consent" in terms
    assert "caveat emptor" in terms
    assert "force majeure" in terms


def test_prefers_longest_phrase():
    text = "The statute of limitations has expired."
    hits = detect_terms(text)
    terms = [item.term.lower() for item in hits]
    assert "statute of limitations" in terms


def test_lookup_search_finds_alias():
    results = lookup("c of o")
    assert results
    assert any("occupancy" in item.term.lower() for item in results)


def test_lookup_empty_query_returns_many():
    results = lookup(None, limit=10)
    assert len(results) == 10
    assert results[0].pidgin_term
    assert results[0].explanation
