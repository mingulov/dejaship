# DejaShip MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the DejaShip intent ledger - a FastAPI backend with pgvector vector search, MCP endpoint, and TypeScript npx client.

**Architecture:** Monorepo with `backend/` (Python/FastAPI/fastembed/pgvector) serving REST + MCP, and `mcp-client/` (TypeScript) as a thin stdio-to-HTTP bridge. Docker Compose for local dev with pgvector.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2.0 async, asyncpg, pgvector, fastembed, FastMCP, Alembic, pytest, testcontainers, Docker, TypeScript, MCP TypeScript SDK.

---

## Task 1: Initialize Backend Python Project

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/dejaship/__init__.py`
- Create: `backend/src/dejaship/config.py`

**Step 1: Initialize uv project**

```bash
cd backend
uv init --lib --name dejaship
```

Then replace the generated `pyproject.toml` with:

```toml
[project]
name = "dejaship"
version = "0.1.0"
description = "The Global Intent Ledger for AI Agents"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "pgvector>=0.3.0",
    "alembic>=1.14.0",
    "pydantic-settings>=2.0.0",
    "fastembed>=0.4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
    "testcontainers[postgres]>=4.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/dejaship"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 2: Create config module**

Create `backend/src/dejaship/config.py`:

```python
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
```

Create `backend/src/dejaship/__init__.py` (empty file).

**Step 3: Install dependencies**

```bash
cd backend && uv sync --all-extras
```

**Step 4: Commit**

```bash
git add backend/
git commit -m "feat: initialize backend project with uv and config"
```

---

## Task 2: Database Models and Engine

**Files:**
- Create: `backend/src/dejaship/db.py`
- Create: `backend/src/dejaship/models.py`

**Step 1: Create async database engine**

Create `backend/src/dejaship/db.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from dejaship.config import settings

engine = create_async_engine(settings.DATABASE_URL)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

**Step 2: Create ORM models**

Create `backend/src/dejaship/models.py`:

```python
import enum
from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
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
    status: Mapped[IntentStatus] = mapped_column(
        Enum(IntentStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default="in_progress",
    )
    edit_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_url: Mapped[str | None] = mapped_column(Text, nullable=True)
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
```

**Step 3: Commit**

```bash
git add backend/src/dejaship/db.py backend/src/dejaship/models.py
git commit -m "feat: add database engine and AgentIntent ORM model"
```

---

## Task 3: Alembic Migrations Setup

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/` (initial migration)

**Step 1: Initialize Alembic**

```bash
cd backend && uv run alembic init alembic
```

**Step 2: Edit `backend/alembic/env.py`**

Replace the generated `env.py` to use async engine and import our models:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from dejaship.config import settings
from dejaship.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(settings.DATABASE_URL)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

**Step 3: Update `backend/alembic.ini`**

Set the `sqlalchemy.url` line to empty (we use settings instead):

```ini
sqlalchemy.url =
```

**Step 4: Generate initial migration**

```bash
cd backend && uv run alembic revision --autogenerate -m "initial schema"
```

**Step 5: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: add Alembic async migration setup with initial schema"
```

---

## Task 4: Embeddings Module

**Files:**
- Create: `backend/src/dejaship/embeddings.py`

**Step 1: Create embeddings wrapper**

Create `backend/src/dejaship/embeddings.py`:

```python
import numpy as np
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
```

**Step 2: Commit**

```bash
git add backend/src/dejaship/embeddings.py
git commit -m "feat: add fastembed wrapper with keyword weighting"
```

---

## Task 5: Pydantic Request/Response Schemas

**Files:**
- Create: `backend/src/dejaship/schemas.py`

**Step 1: Create schemas**

Create `backend/src/dejaship/schemas.py`:

```python
import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from dejaship.config import settings

KEYWORD_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]{1,2}$")


class IntentInput(BaseModel):
    core_mechanic: str = Field(..., min_length=1, max_length=settings.CORE_MECHANIC_MAX_LENGTH)
    keywords: list[str] = Field(..., min_length=settings.MIN_KEYWORDS)

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: list[str]) -> list[str]:
        for kw in v:
            if len(kw) < settings.KEYWORD_MIN_LENGTH or len(kw) > settings.KEYWORD_MAX_LENGTH:
                raise ValueError(
                    f"Each keyword must be {settings.KEYWORD_MIN_LENGTH}-{settings.KEYWORD_MAX_LENGTH} chars, got '{kw}'"
                )
            if not KEYWORD_PATTERN.match(kw):
                raise ValueError(
                    f"Keywords must be lowercase alphanumeric with hyphens, got '{kw}'"
                )
        return v


class NeighborhoodDensity(BaseModel):
    in_progress: int
    shipped: int
    abandoned: int


class ActiveClaim(BaseModel):
    mechanic: str
    status: str
    age_hours: float


class CheckResponse(BaseModel):
    neighborhood_density: NeighborhoodDensity
    closest_active_claims: list[ActiveClaim]


class ClaimResponse(BaseModel):
    claim_id: UUID
    edit_token: str
    status: str
    timestamp: datetime


class UpdateInput(BaseModel):
    claim_id: UUID
    edit_token: str
    status: str = Field(..., pattern=r"^(shipped|abandoned)$")
    resolution_url: str | None = None


class UpdateResponse(BaseModel):
    success: bool
```

**Step 2: Commit**

```bash
git add backend/src/dejaship/schemas.py
git commit -m "feat: add Pydantic request/response schemas with validation"
```

---

## Task 6: Service Layer (Core Business Logic)

**Files:**
- Create: `backend/src/dejaship/services.py`

**Step 1: Create services module**

Create `backend/src/dejaship/services.py`:

```python
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.config import settings
from dejaship.embeddings import build_embedding_text, embed_text
from dejaship.models import AgentIntent, IntentStatus
from dejaship.schemas import (
    ActiveClaim,
    CheckResponse,
    ClaimResponse,
    IntentInput,
    NeighborhoodDensity,
    UpdateInput,
    UpdateResponse,
)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def check_airspace(input: IntentInput, session: AsyncSession) -> CheckResponse:
    text = build_embedding_text(input.core_mechanic, input.keywords)
    vector = embed_text(text)

    # Query for similar intents within threshold using cosine distance
    # cosine_distance = 1 - cosine_similarity, so threshold becomes 1 - similarity
    distance_threshold = 1.0 - settings.SIMILARITY_THRESHOLD

    distance_expr = AgentIntent.embedding.cosine_distance(vector)

    # Count by status
    count_query = (
        select(
            AgentIntent.status,
            func.count().label("cnt"),
        )
        .where(distance_expr <= distance_threshold)
        .group_by(AgentIntent.status)
    )
    result = await session.execute(count_query)
    counts = {row.status: row.cnt for row in result}

    density = NeighborhoodDensity(
        in_progress=counts.get(IntentStatus.IN_PROGRESS, 0),
        shipped=counts.get(IntentStatus.SHIPPED, 0),
        abandoned=counts.get(IntentStatus.ABANDONED, 0),
    )

    # Get closest active claims
    now = datetime.now(timezone.utc)
    closest_query = (
        select(AgentIntent)
        .where(distance_expr <= distance_threshold)
        .where(AgentIntent.status != IntentStatus.ABANDONED)
        .order_by(distance_expr)
        .limit(settings.MAX_CLOSEST_RESULTS)
    )
    result = await session.execute(closest_query)
    closest = []
    for intent in result.scalars():
        age_hours = (now - intent.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        closest.append(
            ActiveClaim(
                mechanic=intent.core_mechanic,
                status=intent.status.value,
                age_hours=round(age_hours, 1),
            )
        )

    return CheckResponse(neighborhood_density=density, closest_active_claims=closest)


async def claim_intent(input: IntentInput, session: AsyncSession) -> ClaimResponse:
    text = build_embedding_text(input.core_mechanic, input.keywords)
    vector = embed_text(text)

    edit_token = secrets.token_urlsafe(32)

    intent = AgentIntent(
        core_mechanic=input.core_mechanic,
        keywords=input.keywords,
        embedding=vector,
        edit_token_hash=_hash_token(edit_token),
    )
    session.add(intent)
    await session.commit()
    await session.refresh(intent)

    return ClaimResponse(
        claim_id=intent.id,
        edit_token=edit_token,
        status=intent.status.value,
        timestamp=intent.created_at,
    )


async def update_claim(input: UpdateInput, session: AsyncSession) -> UpdateResponse:
    intent = await session.get(AgentIntent, input.claim_id)
    if intent is None:
        raise ValueError("Claim not found")

    # Constant-time token comparison
    if not hmac.compare_digest(_hash_token(input.edit_token), intent.edit_token_hash):
        raise PermissionError("Invalid edit token")

    # Validate state transition
    if intent.status != IntentStatus.IN_PROGRESS:
        raise ValueError(f"Cannot transition from {intent.status.value}")

    intent.status = IntentStatus(input.status)
    intent.resolution_url = input.resolution_url
    intent.updated_at = datetime.now(timezone.utc)
    await session.commit()

    return UpdateResponse(success=True)
```

**Step 2: Commit**

```bash
git add backend/src/dejaship/services.py
git commit -m "feat: add service layer with check, claim, update logic"
```

---

## Task 7: REST API Endpoints

**Files:**
- Create: `backend/src/dejaship/api/__init__.py`
- Create: `backend/src/dejaship/api/check.py`
- Create: `backend/src/dejaship/api/claim.py`
- Create: `backend/src/dejaship/api/update.py`

**Step 1: Create API routes**

Create `backend/src/dejaship/api/__init__.py` (empty file).

Create `backend/src/dejaship/api/check.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.db import get_session
from dejaship.schemas import CheckResponse, IntentInput
from dejaship.services import check_airspace

router = APIRouter()


@router.post("/check", response_model=CheckResponse)
async def check(input: IntentInput, session: AsyncSession = Depends(get_session)):
    return await check_airspace(input, session)
```

Create `backend/src/dejaship/api/claim.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.db import get_session
from dejaship.schemas import ClaimResponse, IntentInput
from dejaship.services import claim_intent

router = APIRouter()


@router.post("/claim", response_model=ClaimResponse)
async def claim(input: IntentInput, session: AsyncSession = Depends(get_session)):
    return await claim_intent(input, session)
```

Create `backend/src/dejaship/api/update.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.db import get_session
from dejaship.schemas import UpdateInput, UpdateResponse
from dejaship.services import update_claim

router = APIRouter()


@router.post("/update", response_model=UpdateResponse)
async def update(input: UpdateInput, session: AsyncSession = Depends(get_session)):
    try:
        return await update_claim(input, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
```

**Step 2: Commit**

```bash
git add backend/src/dejaship/api/
git commit -m "feat: add REST endpoints for check, claim, update"
```

---

## Task 8: MCP Server (Streamable HTTP)

**Files:**
- Create: `backend/src/dejaship/mcp/__init__.py`
- Create: `backend/src/dejaship/mcp/server.py`

**Step 1: Create MCP server**

Create `backend/src/dejaship/mcp/__init__.py` (empty file).

Create `backend/src/dejaship/mcp/server.py`:

```python
from mcp.server.fastmcp import FastMCP

from dejaship.db import async_session
from dejaship.schemas import IntentInput, UpdateInput
from dejaship.services import check_airspace, claim_intent, update_claim

mcp = FastMCP(
    "DejaShip",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
async def dejaship_check_airspace(
    core_mechanic: str,
    keywords: list[str],
) -> dict:
    """Check the semantic neighborhood density for a project idea.

    Before building something, check how many other agents are already building
    similar projects. Returns density counts by status and the closest active claims.

    Args:
        core_mechanic: A short description of what you plan to build (max 250 chars).
        keywords: 5+ lowercase keywords describing the project (each 3-40 chars, alphanumeric + hyphens).
    """
    input = IntentInput(core_mechanic=core_mechanic, keywords=keywords)
    async with async_session() as session:
        result = await check_airspace(input, session)
    return result.model_dump()


@mcp.tool()
async def dejaship_claim_intent(
    core_mechanic: str,
    keywords: list[str],
) -> dict:
    """Claim an intent to build a specific project idea.

    Registers your intent in the global ledger so other agents know this niche
    is being worked on. Returns a claim_id and secret edit_token for future updates.

    Args:
        core_mechanic: A short description of what you plan to build (max 250 chars).
        keywords: 5+ lowercase keywords describing the project (each 3-40 chars, alphanumeric + hyphens).
    """
    input = IntentInput(core_mechanic=core_mechanic, keywords=keywords)
    async with async_session() as session:
        result = await claim_intent(input, session)
    return result.model_dump(mode="json")


@mcp.tool()
async def dejaship_update_claim(
    claim_id: str,
    edit_token: str,
    status: str,
    resolution_url: str | None = None,
) -> dict:
    """Update the status of a previously claimed intent.

    Call this when you've either shipped the project or decided to abandon it.

    Args:
        claim_id: The UUID returned from dejaship_claim_intent.
        edit_token: The secret token returned from dejaship_claim_intent.
        status: Either "shipped" or "abandoned".
        resolution_url: The live URL if status is "shipped" (optional).
    """
    input = UpdateInput(
        claim_id=claim_id,
        edit_token=edit_token,
        status=status,
        resolution_url=resolution_url,
    )
    async with async_session() as session:
        try:
            result = await update_claim(input, session)
            return result.model_dump()
        except (ValueError, PermissionError) as e:
            return {"success": False, "error": str(e)}
```

**Step 2: Commit**

```bash
git add backend/src/dejaship/mcp/
git commit -m "feat: add MCP server with 3 tools via Streamable HTTP"
```

---

## Task 9: FastAPI Application Entry Point

**Files:**
- Create: `backend/src/dejaship/main.py`

**Step 1: Create main app**

Create `backend/src/dejaship/main.py`:

```python
import contextlib

from fastapi import FastAPI
from starlette.routing import Mount

from dejaship.api.check import router as check_router
from dejaship.api.claim import router as claim_router
from dejaship.api.update import router as update_router
from dejaship.embeddings import load_model
from dejaship.mcp.server import mcp


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load embedding model
    load_model()
    # Start MCP session manager
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="DejaShip",
    description="The Global Intent Ledger for AI Agents",
    version="0.1.0",
    lifespan=lifespan,
)

# REST API routes
app.include_router(check_router, prefix="/v1")
app.include_router(claim_router, prefix="/v1")
app.include_router(update_router, prefix="/v1")

# MCP endpoint
app.router.routes.append(Mount("/mcp", app=mcp.streamable_http_app()))


@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 2: Verify it starts (syntax check)**

```bash
cd backend && uv run python -c "from dejaship.main import app; print('App created:', app.title)"
```

**Step 3: Commit**

```bash
git add backend/src/dejaship/main.py
git commit -m "feat: add FastAPI app with REST + MCP mounting and lifespan"
```

---

## Task 10: Docker Setup

**Files:**
- Create: `backend/Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`

**Step 1: Create backend Dockerfile**

Create `backend/Dockerfile`:

```dockerfile
# Stage 1: Download embedding model at build time
FROM python:3.12-slim AS model-downloader

RUN pip install --no-cache-dir fastembed

ARG EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='${EMBEDDING_MODEL}')"

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy baked model from build stage
COPY --from=model-downloader /root/.cache/fastembed /root/.cache/fastembed

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "dejaship.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Create Docker Compose**

Create `docker-compose.yml` at repo root:

```yaml
services:
  db:
    image: pgvector/pgvector:pg17
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: dejaship
      POSTGRES_USER: dejaship
      POSTGRES_PASSWORD: dejaship
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dejaship"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DEJASHIP_DATABASE_URL: postgresql+asyncpg://dejaship:dejaship@db:5432/dejaship
      DEJASHIP_EMBEDDING_MODEL: BAAI/bge-base-en-v1.5
    depends_on:
      db:
        condition: service_healthy

volumes:
  pgdata:
```

**Step 3: Create .env.example**

Create `.env.example` at repo root:

```env
# Database
DEJASHIP_DATABASE_URL=postgresql+asyncpg://dejaship:dejaship@localhost:5432/dejaship

# Embedding model (must be supported by fastembed)
DEJASHIP_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
DEJASHIP_VECTOR_DIMENSIONS=768

# Search tuning
DEJASHIP_SIMILARITY_THRESHOLD=0.75
DEJASHIP_MAX_CLOSEST_RESULTS=10
DEJASHIP_KEYWORD_REPEAT=2

# Validation
DEJASHIP_MIN_KEYWORDS=5
DEJASHIP_KEYWORD_MIN_LENGTH=3
DEJASHIP_KEYWORD_MAX_LENGTH=40
DEJASHIP_CORE_MECHANIC_MAX_LENGTH=250

# Cleanup
DEJASHIP_ABANDONMENT_DAYS=7
```

**Step 4: Commit**

```bash
git add backend/Dockerfile docker-compose.yml .env.example
git commit -m "feat: add Docker setup with multi-stage build and compose"
```

---

## Task 11: Integration Tests

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_api.py`

**Step 1: Create test fixtures**

Create `backend/tests/__init__.py` (empty file).

Create `backend/tests/conftest.py`:

```python
import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from dejaship.db import get_session
from dejaship.embeddings import load_model
from dejaship.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer(
        image="pgvector/pgvector:pg17",
        username="test",
        password="test",
        dbname="test",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def embedding_model():
    return load_model()


@pytest.fixture(scope="session")
async def engine(postgres_container):
    url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    eng = create_async_engine(url)

    # Enable pgvector extension and create tables
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        # Rollback to keep tests isolated
        await session.rollback()


@pytest.fixture
async def client(engine, embedding_model) -> AsyncGenerator[AsyncClient, None]:
    from dejaship.main import app

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()
```

**Step 2: Create integration tests**

Create `backend/tests/test_api.py`:

```python
import pytest


SAMPLE_KEYWORDS_SEO = ["seo", "plumber", "local-business", "marketing", "website"]
SAMPLE_KEYWORDS_KNITTING = ["knitting", "inventory", "shop-management", "yarn", "crafts"]


@pytest.mark.asyncio
async def test_check_empty_db(client):
    """Returns zero density on fresh database."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["neighborhood_density"]["in_progress"] == 0
    assert data["neighborhood_density"]["shipped"] == 0
    assert data["neighborhood_density"]["abandoned"] == 0
    assert data["closest_active_claims"] == []


@pytest.mark.asyncio
async def test_claim_returns_token(client):
    """Creates record and returns claim_id + edit_token."""
    resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "claim_id" in data
    assert "edit_token" in data
    assert data["status"] == "in_progress"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_check_finds_similar(client):
    """Claim one idea, check a similar idea → density > 0."""
    # Claim first
    await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    # Check similar
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo for local plumbing businesses",
        "keywords": ["seo", "plumbing", "local-business", "website", "marketing"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["neighborhood_density"]["in_progress"] >= 1


@pytest.mark.asyncio
async def test_check_ignores_dissimilar(client):
    """Claim one idea, check a totally different idea → density = 0."""
    # Claim first
    await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    # Check dissimilar
    resp = await client.post("/v1/check", json={
        "core_mechanic": "knitting inventory predictor",
        "keywords": SAMPLE_KEYWORDS_KNITTING,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["neighborhood_density"]["in_progress"] == 0


@pytest.mark.asyncio
async def test_update_shipped(client):
    """Update claim to shipped with URL."""
    claim_resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    claim = claim_resp.json()

    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
        "resolution_url": "https://example.com",
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_update_abandoned(client):
    """Update claim to abandoned."""
    claim_resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    claim = claim_resp.json()

    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "abandoned",
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_update_wrong_token(client):
    """Reject update with wrong edit_token → 403."""
    claim_resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    claim = claim_resp.json()

    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": "wrong-token",
        "status": "shipped",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_invalid_transition(client):
    """Cannot transition from abandoned back to in_progress."""
    claim_resp = await client.post("/v1/claim", json={
        "core_mechanic": "seo tool for plumbers",
        "keywords": SAMPLE_KEYWORDS_SEO,
    })
    claim = claim_resp.json()

    # First abandon
    await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "abandoned",
    })
    # Try to ship after abandoning
    resp = await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_keyword_validation_too_few(client):
    """Reject fewer than 5 keywords."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool",
        "keywords": ["seo", "plumber"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_keyword_validation_bad_format(client):
    """Reject keywords with invalid characters."""
    resp = await client.post("/v1/check", json={
        "core_mechanic": "seo tool",
        "keywords": ["SEO", "Plumber", "local business", "MARKETING", "website"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_health(client):
    """Health endpoint returns ok."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

**Step 3: Run tests**

```bash
cd backend && uv run pytest tests/ -v
```

Expected: All tests pass (requires Docker running for testcontainers).

**Step 4: Commit**

```bash
git add backend/tests/
git commit -m "feat: add integration tests with testcontainers pgvector"
```

---

## Task 12: Stale Claim Cleanup Script

**Files:**
- Create: `backend/scripts/abandon_stale.py`

**Step 1: Create cleanup script**

Create `backend/scripts/abandon_stale.py`:

```python
"""Cron job: mark stale in_progress claims as abandoned.

Usage: uv run python scripts/abandon_stale.py
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from dejaship.config import settings
from dejaship.db import engine
from dejaship.models import AgentIntent, IntentStatus


async def abandon_stale():
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ABANDONMENT_DAYS)
    async with engine.begin() as conn:
        result = await conn.execute(
            update(AgentIntent)
            .where(AgentIntent.status == IntentStatus.IN_PROGRESS)
            .where(AgentIntent.updated_at < cutoff)
            .values(status=IntentStatus.ABANDONED, updated_at=datetime.now(timezone.utc))
        )
        print(f"Abandoned {result.rowcount} stale claims")


if __name__ == "__main__":
    asyncio.run(abandon_stale())
```

**Step 2: Commit**

```bash
git add backend/scripts/
git commit -m "feat: add stale claim cleanup script"
```

---

## Task 13: TypeScript MCP Client (npx wrapper)

**Files:**
- Create: `mcp-client/package.json`
- Create: `mcp-client/tsconfig.json`
- Create: `mcp-client/src/index.ts`

**Step 1: Create package.json**

Create `mcp-client/package.json`:

```json
{
  "name": "dejaship-mcp",
  "version": "0.1.0",
  "description": "MCP server for DejaShip - The Global Intent Ledger for AI Agents",
  "license": "MIT",
  "type": "module",
  "bin": {
    "dejaship-mcp": "./build/index.js"
  },
  "scripts": {
    "build": "tsc",
    "start": "node build/index.js"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.12.0"
  },
  "devDependencies": {
    "typescript": "^5.7.0",
    "@types/node": "^22.0.0"
  }
}
```

**Step 2: Create tsconfig.json**

Create `mcp-client/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "Node16",
    "moduleResolution": "Node16",
    "outDir": "./build",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "declaration": true
  },
  "include": ["src/**/*"]
}
```

**Step 3: Create MCP stdio server**

Create `mcp-client/src/index.ts`:

```typescript
#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const API_URL = process.env.DEJASHIP_API_URL ?? "https://api.dejaship.com";

async function apiCall(endpoint: string, body: unknown): Promise<unknown> {
  const resp = await fetch(`${API_URL}/v1/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`API error ${resp.status}: ${text}`);
  }
  return resp.json();
}

const server = new McpServer({
  name: "dejaship-mcp",
  version: "0.1.0",
});

server.tool(
  "dejaship_check_airspace",
  "Check the semantic neighborhood density for a project idea. Returns how many agents are building similar projects.",
  {
    core_mechanic: z.string().min(1).max(250).describe("Short description of what you plan to build"),
    keywords: z.array(z.string().min(3).max(40)).min(5).describe("5+ lowercase keywords describing the project"),
  },
  async ({ core_mechanic, keywords }) => {
    const result = await apiCall("check", { core_mechanic, keywords });
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "dejaship_claim_intent",
  "Claim an intent to build a project. Registers your intent so other agents know this niche is taken. Save the returned edit_token for future updates.",
  {
    core_mechanic: z.string().min(1).max(250).describe("Short description of what you plan to build"),
    keywords: z.array(z.string().min(3).max(40)).min(5).describe("5+ lowercase keywords describing the project"),
  },
  async ({ core_mechanic, keywords }) => {
    const result = await apiCall("claim", { core_mechanic, keywords });
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "dejaship_update_claim",
  "Update the status of a previously claimed intent. Call when you've shipped or abandoned the project.",
  {
    claim_id: z.string().uuid().describe("The claim_id from dejaship_claim_intent"),
    edit_token: z.string().describe("The secret edit_token from dejaship_claim_intent"),
    status: z.enum(["shipped", "abandoned"]).describe("New status"),
    resolution_url: z.string().url().optional().describe("Live URL if shipped"),
  },
  async ({ claim_id, edit_token, status, resolution_url }) => {
    const result = await apiCall("update", { claim_id, edit_token, status, resolution_url });
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("DejaShip MCP server running on stdio");
}

main().catch(console.error);
```

**Step 4: Install dependencies and build**

```bash
cd mcp-client && npm install && npm run build
```

**Step 5: Commit**

```bash
git add mcp-client/
git commit -m "feat: add TypeScript MCP client for npx distribution"
```

---

## Task 14: CLAUDE.md and Repository Documentation

**Files:**
- Create: `CLAUDE.md`
- Update: `README.md`

**Step 1: Create CLAUDE.md**

Create `CLAUDE.md` at repo root:

```markdown
# DejaShip Development Guide

## Project Structure

Monorepo with two packages:
- `backend/` - Python FastAPI server (REST API + MCP endpoint)
- `mcp-client/` - TypeScript MCP stdio client (npx wrapper)

## Quick Start

```bash
# Start pgvector + backend
docker compose up --build

# Run migrations
cd backend && uv run alembic upgrade head

# Run tests (requires Docker for testcontainers)
cd backend && uv run pytest tests/ -v
```

## Backend Commands

```bash
cd backend
uv sync --all-extras     # Install all deps
uv run uvicorn dejaship.main:app --reload  # Dev server
uv run alembic upgrade head                # Run migrations
uv run alembic revision --autogenerate -m "description"  # New migration
uv run pytest tests/ -v                    # Run tests
uv run python scripts/abandon_stale.py     # Cleanup stale claims
```

## MCP Client Commands

```bash
cd mcp-client
npm install && npm run build   # Build
node build/index.js            # Run locally
```

## Architecture

- REST endpoints at `/v1/check`, `/v1/claim`, `/v1/update`
- MCP Streamable HTTP at `/mcp`
- Both REST and MCP call shared `services.py`
- Embeddings via fastembed (ONNX, configurable model)
- pgvector for vector similarity search

## Environment Variables

All prefixed with `DEJASHIP_`. See `.env.example` for full list.
Key: `DATABASE_URL`, `EMBEDDING_MODEL`, `SIMILARITY_THRESHOLD`.

## Conventions

- Python: async everywhere, SQLAlchemy 2.0 style, Pydantic for validation
- Tests: integration tests with real pgvector via testcontainers
- Commits: conventional commits (feat/fix/docs/refactor)
```

**Step 2: Update README.md**

Update the existing `README.md` with basic usage info (keep it brief, link to docs).

**Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: add CLAUDE.md and update README"
```

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | Initialize backend project | `pyproject.toml`, `config.py` |
| 2 | Database models and engine | `db.py`, `models.py` |
| 3 | Alembic migrations | `alembic/env.py`, initial migration |
| 4 | Embeddings module | `embeddings.py` |
| 5 | Pydantic schemas | `schemas.py` |
| 6 | Service layer | `services.py` |
| 7 | REST API endpoints | `api/check.py`, `api/claim.py`, `api/update.py` |
| 8 | MCP server | `mcp/server.py` |
| 9 | FastAPI app entry point | `main.py` |
| 10 | Docker setup | `Dockerfile`, `docker-compose.yml` |
| 11 | Integration tests | `conftest.py`, `test_api.py` |
| 12 | Stale cleanup script | `scripts/abandon_stale.py` |
| 13 | TypeScript MCP client | `mcp-client/src/index.ts` |
| 14 | Documentation | `CLAUDE.md`, `README.md` |
