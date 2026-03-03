"""HTTP request/response access logging middleware.

Logs one structured JSON line per request to stdout via the standard
logging module. Docker captures this automatically; filter with:

    docker compose logs backend | grep request_log | jq .
    docker compose logs backend | grep request_log | jq 'select(.path == "/v1/check")'
"""

import json
import logging
import time
from datetime import datetime, timezone

from fastapi import Request
from starlette.responses import Response

access_logger = logging.getLogger("dejaship.access")

_SKIP_PATHS = frozenset({"/health", "/ready"})
_REDACT_FIELDS = frozenset({"edit_token"})


def _redact(data: dict) -> dict:
    """Return a copy of data with sensitive fields replaced by [REDACTED]."""
    if not any(f in data for f in _REDACT_FIELDS):
        return data
    return {k: "[REDACTED]" if k in _REDACT_FIELDS else v for k, v in data.items()}


async def access_log_middleware(request: Request, call_next) -> Response:
    """Log API requests and responses as structured JSON.

    Skips health checks and the streaming MCP endpoint.
    Redacts sensitive fields from request and response bodies.
    Never raises — a logging failure must not affect the real request.
    """
    path = request.url.path
    if path in _SKIP_PATHS or path.startswith("/mcp"):
        return await call_next(request)

    start = time.monotonic()

    # Read and cache request body. Starlette caches the result of body()
    # so downstream route handlers can still read it.
    req_bytes = await request.body()

    req_data: dict = {}
    try:
        if req_bytes:
            req_data = _redact(json.loads(req_bytes))
    except Exception:
        pass

    response = await call_next(request)
    latency_ms = int((time.monotonic() - start) * 1000)

    # Collect response body chunks and rebuild the response.
    # (Iterating body_iterator consumes it; we must reconstruct.)
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
    resp_bytes = b"".join(chunks)

    resp_data: dict = {}
    try:
        if resp_bytes:
            resp_data = _redact(json.loads(resp_bytes))
    except Exception:
        pass

    try:
        ip = request.headers.get("CF-Connecting-IP") or (
            request.client.host if request.client else "?"
        )
        access_logger.info(
            json.dumps({
                "type": "request_log",
                "ts": datetime.now(timezone.utc).isoformat(),
                "path": path,
                "method": request.method,
                "status": response.status_code,
                "latency_ms": latency_ms,
                "ip": ip,
                "ua": request.headers.get("User-Agent", ""),
                "req": req_data,
                "resp": resp_data,
            })
        )
    except Exception:
        pass  # Never let a logging failure affect a real request

    return Response(
        content=resp_bytes,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )
