import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from dejaship.config import settings


class Base(DeclarativeBase):
    pass


class IntentStatus(enum.Enum):
    IN_PROGRESS = "in_progress"
    SHIPPED = "shipped"
    ABANDONED = "abandoned"


class AgentIntent(Base):
    __tablename__ = "agent_intents"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    core_mechanic: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False)
    embedding = mapped_column(Vector(settings.VECTOR_DIMENSIONS), nullable=False)
    mechanic_embedding = mapped_column(Vector(settings.VECTOR_DIMENSIONS), nullable=True)
    status: Mapped[IntentStatus] = mapped_column(
        Enum(IntentStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default="in_progress",
    )
    edit_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_tsvector: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "idx_intents_embedding",
            embedding,
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_intents_status", "status"),
    )
