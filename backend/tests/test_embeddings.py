"""Unit tests for the embeddings module."""

from dejaship.config import settings
from dejaship.embeddings import build_embedding_text, clean_keywords, embed_text, load_model


def test_build_embedding_text_basic():
    """First 10 keywords repeated KEYWORD_REPEAT times, core_mechanic appended once."""
    text = build_embedding_text("my tool", ["alpha", "beta", "gamma", "delta", "echo"])
    # With KEYWORD_REPEAT=2 and 5 keywords (all primary):
    # alpha beta gamma delta echo alpha beta gamma delta echo my tool
    parts = text.split()
    # Each keyword appears twice (repeated), plus core_mechanic words once
    assert parts.count("alpha") == 2
    assert parts.count("beta") == 2
    assert parts[-2:] == ["my", "tool"]


def test_build_embedding_text_more_than_10():
    """Keywords beyond 10 are included once, not repeated."""
    keywords = [f"kw{i}" for i in range(15)]
    text = build_embedding_text("test mechanic", keywords)
    parts = text.split()
    # First 10 keywords repeated 2x, remaining 5 included 1x
    for i in range(10):
        assert parts.count(f"kw{i}") == 2
    for i in range(10, 15):
        assert parts.count(f"kw{i}") == 1


def test_embed_text_returns_768_dim():
    """Embedding vector has 768 dimensions."""
    load_model()
    vector = embed_text("test input string")
    assert len(vector) == 768
    assert all(isinstance(v, float) for v in vector)


def test_embed_text_normalized():
    """BGE model produces unit-norm vectors (required for cosine similarity)."""
    import math
    load_model()
    vector = embed_text("seo tool for plumbers")
    norm = math.sqrt(sum(v ** 2 for v in vector))
    assert abs(norm - 1.0) < 0.01  # within 1% of unit norm


def test_build_embedding_text_exactly_10_keywords():
    """Exactly 10 keywords: all are primary (repeated), none secondary."""
    keywords = [f"kw{i}" for i in range(10)]
    text = build_embedding_text("mechanic", keywords)
    parts = text.split()
    for i in range(10):
        assert parts.count(f"kw{i}") == 2


def test_build_embedding_text_core_mechanic_always_last():
    """core_mechanic is always appended after all keywords."""
    text = build_embedding_text("UNIQUE_MECHANIC", ["alpha", "beta", "gamma", "delta", "echo"])
    assert text.endswith("UNIQUE_MECHANIC")


def test_build_embedding_text_empty_secondary():
    """With ≤10 keywords, secondary list is empty (no extra keywords appended once)."""
    keywords = ["alpha", "beta", "gamma", "delta", "echo"]
    text = build_embedding_text("mechanic", keywords)
    parts = text.split()
    # Only primary keywords (repeated 2x) and mechanic - no secondary
    expected_count = len(keywords) * 2 + 1  # +1 for "mechanic"
    assert len(parts) == expected_count


def test_clean_keywords_removes_stopwords():
    """Stopwords are removed from keyword list."""
    stopwords = {"and", "the", "saas"}
    result = clean_keywords(["hvac", "and", "saas", "subscription"], stopwords)
    assert result == ["hvac", "subscription"]


def test_clean_keywords_removes_single_chars():
    """Single-character keywords are always removed."""
    result = clean_keywords(["a", "hvac", "b"], set())
    assert result == ["hvac"]


def test_clean_keywords_case_insensitive():
    """Stopword matching is case-insensitive."""
    stopwords = {"saas"}
    result = clean_keywords(["HVAC", "SaaS", "billing"], stopwords)
    assert result == ["HVAC", "billing"]


def test_clean_keywords_preserves_order():
    """Order of non-stopword keywords is preserved."""
    stopwords = {"remove"}
    result = clean_keywords(["crm", "analytics", "billing"], stopwords)
    assert result == ["crm", "analytics", "billing"]


def test_clean_keywords_empty_input():
    assert clean_keywords([], {"saas"}) == []


def test_build_embedding_text_applies_cleanup_when_enabled(monkeypatch):
    """build_embedding_text strips stopwords when ENABLE_KEYWORD_CLEANUP is True."""
    monkeypatch.setattr(settings, "ENABLE_KEYWORD_CLEANUP", True)
    monkeypatch.setattr(settings, "KEYWORD_STOPWORDS", "saas,renewals")
    text = build_embedding_text("billing tool", ["saas", "crm", "renewals", "invoicing"])
    words = text.split()
    assert "saas" not in words
    assert "renewals" not in words
    assert "crm" in words
    assert "invoicing" in words


def test_parse_stopwords_includes_nltk_when_enabled():
    """When use_nltk=True, NLTK English stopwords are merged into the set."""
    from dejaship.embeddings import _parse_stopwords
    result = _parse_stopwords("saas,renewals", True)
    # NLTK English list includes common words like "the", "and", "is"
    assert "the" in result
    assert "and" in result
    assert "is" in result
    # Manual words still included
    assert "saas" in result
    assert "renewals" in result


def test_parse_stopwords_excludes_nltk_when_disabled():
    """When use_nltk=False, NLTK words not automatically added."""
    from dejaship.embeddings import _parse_stopwords
    result = _parse_stopwords("saas", False)
    # Common NLTK words should NOT be present
    assert "the" not in result
    assert "and" not in result
    # But manual words are still present
    assert "saas" in result


def test_build_embedding_text_uses_nltk_stopwords(monkeypatch):
    """When both ENABLE_KEYWORD_CLEANUP and ENABLE_NLTK_STOPWORDS are True,
    NLTK stopwords are applied to keywords before embedding."""
    from dejaship.config import settings
    from dejaship.embeddings import build_embedding_text
    monkeypatch.setattr(settings, "ENABLE_KEYWORD_CLEANUP", True)
    monkeypatch.setattr(settings, "ENABLE_NLTK_STOPWORDS", True)
    monkeypatch.setattr(settings, "KEYWORD_STOPWORDS", "saas")
    text = build_embedding_text("billing tool", ["saas", "the", "crm", "and"])
    words = text.split()
    # "the" and "and" are in NLTK stopwords → removed
    assert "the" not in words
    assert "and" not in words
    # "crm" is not a stopword → kept
    assert "crm" in words
