from fastembed import TextEmbedding

from dejaship.config import settings

_model: TextEmbedding | None = None


def load_model() -> TextEmbedding:
    global _model
    _model = TextEmbedding(model_name=settings.EMBEDDING_MODEL)
    return _model


def get_model() -> TextEmbedding:
    if _model is None:
        raise RuntimeError("Embedding model not loaded. Call load_model() first.")
    return _model


def clean_keywords(keywords: list[str], stopwords: set[str]) -> list[str]:
    """Remove stopword and single-character keywords."""
    return [kw for kw in keywords if kw.lower() not in stopwords and len(kw) > 1]


def build_embedding_text(core_mechanic: str, keywords: list[str]) -> str:
    """Build weighted embedding text from keywords and optionally the core_mechanic.

    Strategy (controlled by DEJASHIP_ env vars):
    - EMBEDDING_INCLUDE_CORE_MECHANIC (default True): append core_mechanic after keywords.
      Set to false for keywords-only mode. Tested 2026-03-02 — keywords-only hurt recall
      on the coverage-max corpus; keep True. See docs/decisions/2026-03-02-embedding-text-strategy.md
    - KEYWORD_REPEAT (default 2): repeat the first 10 keywords N times for emphasis.
    - ENABLE_KEYWORD_CLEANUP (default False): remove generic SaaS stopwords before embedding.
    """
    if settings.ENABLE_KEYWORD_CLEANUP:
        stopwords = {s.strip().lower() for s in settings.KEYWORD_STOPWORDS.split(",") if s.strip()}
        keywords = clean_keywords(keywords, stopwords)
    primary = keywords[:10]
    secondary = keywords[10:]
    parts = []
    for _ in range(settings.KEYWORD_REPEAT):
        parts.extend(primary)
    parts.extend(secondary)
    if settings.EMBEDDING_INCLUDE_CORE_MECHANIC:
        parts.append(core_mechanic)
    return " ".join(parts)


def embed_text(text: str) -> list[float]:
    """Generate embedding vector for a single text string."""
    model = get_model()
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()
