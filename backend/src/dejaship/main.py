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
