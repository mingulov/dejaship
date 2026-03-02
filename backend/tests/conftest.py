import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from dejaship.db import get_session
from dejaship.embeddings import load_model
from dejaship.limiter import limiter
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
    eng = create_async_engine(url, poolclass=NullPool)

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
        await session.rollback()


@pytest.fixture
async def client(engine, embedding_model) -> AsyncGenerator[AsyncClient, None]:
    # embedding_model is injected to ensure load_model() runs before any request
    _ = embedding_model
    from dejaship import main

    app = main.app

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    original_engine = main.engine

    async def override_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    main.engine = engine

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    main.engine = original_engine

    # Clean up data between tests for isolation
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM agent_intents"))


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()
