from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://dejaship:dejaship@localhost:5432/dejaship"

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    VECTOR_DIMENSIONS: int = 768

    # Similarity search
    SIMILARITY_THRESHOLD: float = 0.75
    MAX_CLOSEST_RESULTS: int = 10

    # Keyword weighting
    KEYWORD_REPEAT: int = 2

    # Validation
    MIN_KEYWORDS: int = 5
    KEYWORD_MIN_LENGTH: int = 3
    KEYWORD_MAX_LENGTH: int = 40
    CORE_MECHANIC_MAX_LENGTH: int = 250

    # Stale claim cleanup
    ABANDONMENT_DAYS: int = 7

    model_config = {"env_prefix": "DEJASHIP_"}


settings = Settings()
