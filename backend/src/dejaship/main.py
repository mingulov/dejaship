import contextlib

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse
from starlette.routing import Mount

from dejaship.access_log import access_log_middleware
from dejaship.api.check import router as check_router
from dejaship.api.claim import router as claim_router
from dejaship.api.stats import router as stats_router
from dejaship.api.update import router as update_router
from dejaship.config import settings
from dejaship.db import engine
from dejaship.embeddings import get_model, load_model
from dejaship.limiter import limiter
from dejaship.mcp.server import mcp


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load embedding model
    load_model()
    if settings.ENABLE_RERANKER:
        from dejaship.reranker import load_reranker
        load_reranker()  # CPU-bound, same pattern as load_model() above
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

# CORS — allow the landing page to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",")],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Access logging — structured JSON to stdout for beta quality analysis
@app.middleware("http")
async def _access_log(request: Request, call_next):
    return await access_log_middleware(request, call_next)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@limiter.limit(lambda: settings.RATE_LIMIT_MCP)
async def _mcp_rate_limit_marker(request: Request):
    return None


@app.middleware("http")
async def enforce_mcp_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        try:
            limiter._check_request_limit(request, _mcp_rate_limit_marker, in_middleware=False)
        except RateLimitExceeded as exc:
            return _rate_limit_exceeded_handler(request, exc)
    return await call_next(request)

# REST API routes
app.include_router(check_router, prefix="/v1")
app.include_router(claim_router, prefix="/v1")
app.include_router(update_router, prefix="/v1")
app.include_router(stats_router, prefix="/v1")

# MCP endpoint
app.router.routes.append(Mount("/mcp", app=mcp.streamable_http_app()))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    checks = {"database": "ok", "embeddings": "ok"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = "error"

    try:
        get_model()
    except RuntimeError:
        checks["embeddings"] = "error"

    if settings.ENABLE_RERANKER:
        from dejaship.reranker import get_reranker
        checks["reranker"] = "ok"
        try:
            get_reranker()
        except RuntimeError:
            checks["reranker"] = "error"

    status = "ok" if all(value == "ok" for value in checks.values()) else "error"
    status_code = 200 if status == "ok" else 503
    return JSONResponse(status_code=status_code, content={"status": status, "checks": checks})
