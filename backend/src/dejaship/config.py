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

    # Rate limits (requests per minute per IP)
    RATE_LIMIT_CHECK: str = "60/minute"
    RATE_LIMIT_CLAIM: str = "60/minute"
    RATE_LIMIT_UPDATE: str = "60/minute"
    RATE_LIMIT_MCP: str = "60/minute"

    # Proxy trust
    TRUST_PROXY_HEADERS: bool = False
    TRUSTED_PROXY_CIDRS: str = ""

    # Keyword Jaccard post-filter
    # Filters vector search results by keyword set overlap.
    # See docs/search-quality/improvement-approaches.md
    ENABLE_JACCARD_FILTER: bool = False
    JACCARD_THRESHOLD: float = 0.15
    JACCARD_MIN_KEYWORDS: int = 3

    model_config = {"env_prefix": "DEJASHIP_"}


settings = Settings()
