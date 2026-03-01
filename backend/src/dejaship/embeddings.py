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


def build_embedding_text(core_mechanic: str, keywords: list[str]) -> str:
    """Build weighted text for embedding. First 10 keywords repeated for emphasis."""
    primary = keywords[:10]
    secondary = keywords[10:]
    parts = []
    for _ in range(settings.KEYWORD_REPEAT):
        parts.extend(primary)
    parts.extend(secondary)
    parts.append(core_mechanic)
    return " ".join(parts)


def embed_text(text: str) -> list[float]:
    """Generate embedding vector for a single text string."""
    model = get_model()
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()
