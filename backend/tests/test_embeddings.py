"""Unit tests for the embeddings module."""

from dejaship.embeddings import build_embedding_text, embed_text, load_model


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
