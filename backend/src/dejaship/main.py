import contextlib

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.routing import Mount

from dejaship.api.check import router as check_router
from dejaship.api.claim import router as claim_router
from dejaship.api.update import router as update_router
from dejaship.db import engine
from dejaship.embeddings import load_model
from dejaship.limiter import limiter
from dejaship.mcp.server import mcp


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load embedding model
    load_model()
    # Start MCP session manager
    async with mcp.session_manager.run():
        yield
    # Shutdown: release DB connections
    await engine.dispose()


app = FastAPI(
    title="DejaShip",
    description="The Global Intent Ledger for AI Agents",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# REST API routes
app.include_router(check_router, prefix="/v1")
app.include_router(claim_router, prefix="/v1")
app.include_router(update_router, prefix="/v1")

# MCP endpoint
app.router.routes.append(Mount("/mcp", app=mcp.streamable_http_app()))


@app.get("/health")
async def health():
    return {"status": "ok"}
