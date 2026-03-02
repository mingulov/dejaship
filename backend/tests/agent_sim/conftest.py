import contextlib

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.routing import Mount

from dejaship.embeddings import load_model
from tests.agent_sim._support.catalog import (
    load_app_catalog,
    load_model_matrix,
    load_scenario_matrix,
)
from tests.agent_sim._support.fixture_store import load_fixture_index


@pytest.fixture(scope="session")
def agent_sim_catalog():
    return load_app_catalog()


@pytest.fixture(scope="session")
def agent_sim_model_matrix():
    return load_model_matrix()


@pytest.fixture(scope="session")
def agent_sim_scenario_matrix(agent_sim_model_matrix):
    return load_scenario_matrix(agent_sim_model_matrix)


@pytest.fixture(scope="session")
def agent_sim_fixture_index():
    return load_fixture_index()


@pytest.fixture(scope="session")
def mcp_base_url():
    return "http://localhost/mcp/"


@pytest_asyncio.fixture(autouse=True)
async def clear_agent_sim_db(engine):
    yield
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM agent_intents"))


@pytest.fixture
def mcp_http_client_factory(engine, embedding_model):
    _ = embedding_model
    @contextlib.asynccontextmanager
    async def factory():
        from dejaship.mcp import server as mcp_server

        mcp_server.mcp._session_manager = None
        mcp_app = mcp_server.mcp.streamable_http_app()
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        original_async_session = mcp_server.async_session
        original_transport_security = mcp_server.mcp.settings.transport_security.model_copy(deep=True)

        @contextlib.asynccontextmanager
        async def lifespan(app: FastAPI):
            load_model()
            async with mcp_server.mcp.session_manager.run():
                yield

        app = FastAPI(lifespan=lifespan)
        app.router.routes.append(Mount("/mcp", app=mcp_app))

        mcp_server.async_session = session_factory
        mcp_server.mcp.settings.transport_security.enable_dns_rebinding_protection = True
        mcp_server.mcp.settings.transport_security.allowed_hosts = [
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
        ]
        mcp_server.mcp.settings.transport_security.allowed_origins = [
            "http://localhost",
            "http://127.0.0.1",
            "http://localhost:*",
            "http://127.0.0.1:*",
        ]

        try:
            async with app.router.lifespan_context(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://localhost",
                    follow_redirects=True,
                ) as client:
                    yield client
        finally:
            mcp_server.async_session = original_async_session
            mcp_server.mcp.settings.transport_security = original_transport_security

    return factory
