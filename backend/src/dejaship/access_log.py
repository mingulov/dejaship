"""HTTP request/response access logging for beta quality analysis.

Logs structured JSON lines to stdout via Python's standard logging module.
Docker captures this automatically; filter with:

    docker compose logs backend | grep request_log | jq .
    docker compose logs backend | grep mcp_http_log | jq .
    docker compose logs backend | grep mcp_tool_log | jq .
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from starlette.responses import Response

access_logger = logging.getLogger("dejaship.access")
mcp_logger = logging.getLogger("dejaship.mcp_access")

_SKIP_PATHS = frozenset({"/health", "/ready"})
_REDACT_FIELDS = frozenset({"edit_token"})


def _redact(data: dict) -> dict:
    """Return a copy of data with sensitive fields replaced by [REDACTED]."""
    if not any(f in data for f in _REDACT_FIELDS):
        return data
    return {k: "[REDACTED]" if k in _REDACT_FIELDS else v for k, v in data.items()}


def _get_ip(request: Request) -> str:
    return request.headers.get("CF-Connecting-IP") or (
        request.client.host if request.client else "?"
    )


async def access_log_middleware(request: Request, call_next) -> Response:
    """Log API requests and responses as structured JSON.

    - REST endpoints: full log with request and response bodies (``request_log``)
    - /mcp endpoint: metadata only — no response body read (``mcp_http_log``)
    - /health, /ready: skipped entirely

    Redacts sensitive fields. Never raises.
    """
    path = request.url.path
    if path in _SKIP_PATHS:
        return await call_next(request)

    start = time.monotonic()

    # Read and cache request body. Starlette caches the result of body()
    # so downstream route handlers can still read it.
    req_bytes = await request.body()

    # --- MCP path: log metadata only, don't touch the SSE response body ---
    if path.startswith("/mcp"):
        response = await call_next(request)
        latency_ms = int((time.monotonic() - start) * 1000)

        jsonrpc_method = ""
        try:
            if req_bytes:
                jsonrpc_method = json.loads(req_bytes).get("method", "")
        except Exception:
            pass

        try:
            access_logger.info(
                json.dumps({
                    "type": "mcp_http_log",
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "path": path,
                    "method": request.method,
                    "status": response.status_code,
                    "latency_ms": latency_ms,
                    "jsonrpc_method": jsonrpc_method,
                    "ip": _get_ip(request),
                    "ua": request.headers.get("User-Agent", ""),
                })
            )
        except Exception:
            pass

        return response  # Return unmodified — SSE stream stays intact

    # --- REST path: full log with request and response bodies ---
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
        access_logger.info(
            json.dumps({
                "type": "request_log",
                "ts": datetime.now(timezone.utc).isoformat(),
                "path": path,
                "method": request.method,
                "status": response.status_code,
                "latency_ms": latency_ms,
                "ip": _get_ip(request),
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


def log_mcp_tool_call(
    tool_name: str,
    req: dict[str, Any],
    resp: dict[str, Any] | None,
    *,
    latency_ms: int,
    error: str | None = None,
) -> None:
    """Log an MCP tool invocation as structured JSON.

    Call this inside each MCP tool function in server.py.
    Redacts sensitive fields. Never raises.
    """
    entry: dict[str, Any] = {
        "type": "mcp_tool_log",
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "latency_ms": latency_ms,
        "req": _redact(req),
    }
    if resp is not None:
        entry["resp"] = _redact(resp)
    if error is not None:
        entry["error"] = error

    try:
        mcp_logger.info(json.dumps(entry))
    except Exception:
        pass
