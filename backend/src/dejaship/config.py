from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://dejaship:dejaship@localhost:5432/dejaship"

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    VECTOR_DIMENSIONS: int = 768

    # Similarity search
    SIMILARITY_THRESHOLD: float = 0.60
    MAX_CLOSEST_RESULTS: int = 10

    # Keyword weighting
    KEYWORD_REPEAT: int = 2

    # Embedding text construction experiments
    # EMBEDDING_INCLUDE_CORE_MECHANIC=false gives keywords-only embedding.
    # Tested 2026-03-02: keywords-only did NOT improve FPR on coverage-max corpus —
    # it reduced recall too much. Keep true. See docs/decisions/2026-03-02-embedding-text-strategy.md
    EMBEDDING_INCLUDE_CORE_MECHANIC: bool = True

    # Validation
    MIN_KEYWORDS: int = 5
    MAX_KEYWORDS: int = 50
    KEYWORD_MIN_LENGTH: int = 3
    KEYWORD_MAX_LENGTH: int = 40
    CORE_MECHANIC_MAX_LENGTH: int = 250

    # Database pool
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Stale claim cleanup
    ABANDONMENT_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = "https://dejaship.com"

    # Rate limits (requests per minute per IP)
    RATE_LIMIT_CHECK: str = "60/minute"
    RATE_LIMIT_CLAIM: str = "60/minute"
    RATE_LIMIT_UPDATE: str = "60/minute"
    RATE_LIMIT_MCP: str = "60/minute"
    RATE_LIMIT_STATS: str = "120/minute"

    # Proxy trust
    TRUST_PROXY_HEADERS: bool = False
    TRUSTED_PROXY_CIDRS: str = ""

    # Keyword Jaccard post-filter
    # Filters vector search results by keyword set overlap.
    # See docs/search-quality/improvement-approaches.md
    ENABLE_JACCARD_FILTER: bool = False
    JACCARD_THRESHOLD: float = 0.15
    JACCARD_MIN_KEYWORDS: int = 3

    # Keyword stopword cleanup before embedding
    # Removes generic SaaS terms that inflate cross-domain similarity.
    # See docs/search-quality/false-positive-root-cause.md
    ENABLE_KEYWORD_CLEANUP: bool = False
    KEYWORD_STOPWORDS: str = "and,with,the,for,subscription,saas,recurring-revenue,revenue,renewals,retention"

    # NLP keyword preprocessing (requires nlp extras: uv sync --extra nlp)
    # ENABLE_NLTK_STOPWORDS: augments KEYWORD_STOPWORDS with NLTK English stopwords (179 words).
    # ENABLE_SPACY_LEMMATIZATION: lemmatizes keywords before Jaccard comparison so
    #   "renewal" and "renewals" match. Adds ~10ms per request (spaCy CPU inference).
    ENABLE_NLTK_STOPWORDS: bool = False
    ENABLE_SPACY_LEMMATIZATION: bool = False

    # Two-stage retrieval
    # Stage 1: broad candidate retrieval with combined embedding at lower threshold
    # Stage 2: rerank by core_mechanic-only embedding similarity
    # See docs/decisions/2026-03-02-embedding-text-strategy.md
    ENABLE_TWO_STAGE_RETRIEVAL: bool = False
    STAGE1_THRESHOLD: float = 0.55
    STAGE2_THRESHOLD: float = 0.65
    STAGE2_CANDIDATE_MULTIPLIER: int = 3

    # ColBERT reranker (late-interaction reranking)
    # Reranks vector search candidates using ColBERT MaxSim scoring.
    # Adds latency but improves precision.
    # See docs/search-quality/improvement-approaches.md
    ENABLE_RERANKER: bool = False
    RERANKER_MODEL: str = "colbert-ir/colbertv2.0"
    RERANKER_THRESHOLD: float = 0.5

    # Hybrid vector + full-text search
    # Combines vector similarity ranking with PostgreSQL FTS using RRF fusion.
    # See docs/search-quality/improvement-approaches.md
    ENABLE_HYBRID_SEARCH: bool = False
    HYBRID_RRF_K: int = 60
    HYBRID_FTS_WEIGHT: float = 0.3

    model_config = {"env_prefix": "DEJASHIP_"}


settings = Settings()
