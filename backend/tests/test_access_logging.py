"""Tests for HTTP request/response access logging middleware."""

import json
import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from dejaship.access_log import access_log_middleware, log_mcp_tool_call


def _make_app() -> FastAPI:
    """Minimal FastAPI app with access logging middleware — no database needed."""
    app = FastAPI()

    @app.middleware("http")
    async def middleware(request, call_next):
        return await access_log_middleware(request, call_next)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/v1/check")
    async def check(body: dict = {}):
        return {
            "neighborhood_density": {"in_progress": 1, "shipped": 0, "abandoned": 0},
            "closest_active_claims": [],
        }

    @app.post("/v1/claim")
    async def claim(body: dict = {}):
        return {
            "claim_id": "00000000-0000-0000-0000-000000000000",
            "edit_token": "supersecret",
            "status": "in_progress",
            "timestamp": "2026-01-01T00:00:00Z",
        }

    @app.post("/mcp")
    async def mcp_endpoint(request: Request):
        async def stream():
            yield b"data: {}\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


@pytest.fixture(autouse=True)
def _enable_log_propagation():
    """Re-enable propagation so caplog captures our loggers.

    main.py sets propagate=False for production (plain stdout handler).
    Tests need propagation for caplog to work.
    """
    loggers = [logging.getLogger(n) for n in ("dejaship.access", "dejaship.mcp_access")]
    original = [(lg, lg.propagate) for lg in loggers]
    for lg in loggers:
        lg.propagate = True
    yield
    for lg, prop in original:
        lg.propagate = prop


@pytest.fixture
def client():
    return TestClient(_make_app())


class TestAccessLogMiddleware:
    """Middleware logs requests and responses as structured JSON."""

    def test_request_produces_log_entry(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/check", json={"core_mechanic": "test", "keywords": ["a"]})
        assert any("request_log" in r.message for r in caplog.records)

    def test_log_entry_is_valid_json(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/check", json={})
        entry = json.loads(caplog.records[-1].message)
        assert entry["type"] == "request_log"

    def test_log_has_correct_path(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/check", json={})
        entry = json.loads(caplog.records[-1].message)
        assert entry["path"] == "/v1/check"

    def test_log_has_method(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/check", json={})
        entry = json.loads(caplog.records[-1].message)
        assert entry["method"] == "POST"

    def test_log_has_status_code(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/check", json={})
        entry = json.loads(caplog.records[-1].message)
        assert entry["status"] == 200

    def test_log_has_non_negative_latency_ms(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/check", json={})
        entry = json.loads(caplog.records[-1].message)
        assert isinstance(entry["latency_ms"], int)
        assert entry["latency_ms"] >= 0

    def test_log_has_timestamp(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/check", json={})
        entry = json.loads(caplog.records[-1].message)
        assert "ts" in entry
        assert "2026" in entry["ts"]

    def test_log_contains_request_body(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/check", json={"core_mechanic": "invoice tool"})
        entry = json.loads(caplog.records[-1].message)
        assert entry["req"]["core_mechanic"] == "invoice tool"

    def test_log_contains_response_body(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/check", json={})
        entry = json.loads(caplog.records[-1].message)
        assert "neighborhood_density" in entry["resp"]

    def test_response_body_unchanged_by_middleware(self, client):
        """Middleware must not corrupt or alter the actual response."""
        resp = client.post("/v1/check", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "neighborhood_density" in data
        assert "closest_active_claims" in data

    def test_edit_token_redacted_in_request(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/claim", json={"core_mechanic": "test", "edit_token": "supersecret"})
        entry = json.loads(caplog.records[-1].message)
        assert entry["req"]["edit_token"] == "[REDACTED]"
        assert "supersecret" not in caplog.text

    def test_edit_token_redacted_in_response(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/v1/claim", json={})
        entry = json.loads(caplog.records[-1].message)
        assert entry["resp"].get("edit_token") == "[REDACTED]"
        assert "supersecret" not in caplog.text

    def test_health_endpoint_not_logged(self, client, caplog):
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.get("/health")
        assert not any("request_log" in r.message for r in caplog.records)


class TestMcpHttpLogging:
    """HTTP middleware logs metadata for /mcp without reading response body."""

    def test_mcp_request_produces_http_log(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            )
        assert any("mcp_http_log" in r.message for r in caplog.records)

    def test_mcp_http_log_has_path(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        entries = [json.loads(r.message) for r in caplog.records if "mcp_http_log" in r.message]
        assert len(entries) >= 1
        assert entries[0]["path"].startswith("/mcp")

    def test_mcp_http_log_has_latency(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        entries = [json.loads(r.message) for r in caplog.records if "mcp_http_log" in r.message]
        assert entries[0]["latency_ms"] >= 0

    def test_mcp_http_log_has_jsonrpc_method(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}},
            )
        entries = [json.loads(r.message) for r in caplog.records if "mcp_http_log" in r.message]
        assert entries[0]["jsonrpc_method"] == "tools/call"

    def test_mcp_http_log_has_no_response_body(self, client, caplog):
        """Must NOT contain resp key — reading SSE body would break streaming."""
        with caplog.at_level(logging.INFO, logger="dejaship.access"):
            client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        entries = [json.loads(r.message) for r in caplog.records if "mcp_http_log" in r.message]
        assert "resp" not in entries[0]

    def test_mcp_streaming_response_intact(self, client):
        """Middleware must not break the SSE stream."""
        resp = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert resp.status_code == 200


class TestMcpToolLogging:
    """log_mcp_tool_call() logs tool invocations as structured JSON."""

    def test_produces_log_entry(self, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.mcp_access"):
            log_mcp_tool_call(
                "dejaship_check_airspace",
                {"core_mechanic": "test", "keywords": ["a", "b"]},
                {"neighborhood_density": {"in_progress": 0}},
                latency_ms=42,
            )
        assert any("mcp_tool_log" in r.message for r in caplog.records)

    def test_log_has_tool_name(self, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.mcp_access"):
            log_mcp_tool_call("dejaship_check_airspace", {}, {}, latency_ms=0)
        entry = json.loads(caplog.records[-1].message)
        assert entry["tool"] == "dejaship_check_airspace"

    def test_log_has_request_params(self, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.mcp_access"):
            log_mcp_tool_call("check", {"core_mechanic": "invoice tool"}, {}, latency_ms=0)
        entry = json.loads(caplog.records[-1].message)
        assert entry["req"]["core_mechanic"] == "invoice tool"

    def test_log_has_response_data(self, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.mcp_access"):
            log_mcp_tool_call("check", {}, {"neighborhood_density": {}}, latency_ms=5)
        entry = json.loads(caplog.records[-1].message)
        assert "neighborhood_density" in entry["resp"]

    def test_log_has_latency(self, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.mcp_access"):
            log_mcp_tool_call("check", {}, {}, latency_ms=123)
        entry = json.loads(caplog.records[-1].message)
        assert entry["latency_ms"] == 123

    def test_edit_token_redacted_in_request(self, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.mcp_access"):
            log_mcp_tool_call("update", {"edit_token": "secret123"}, {}, latency_ms=0)
        entry = json.loads(caplog.records[-1].message)
        assert entry["req"]["edit_token"] == "[REDACTED]"
        assert "secret123" not in caplog.text

    def test_edit_token_redacted_in_response(self, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.mcp_access"):
            log_mcp_tool_call("claim", {}, {"edit_token": "secret123", "claim_id": "abc"}, latency_ms=0)
        entry = json.loads(caplog.records[-1].message)
        assert entry["resp"]["edit_token"] == "[REDACTED]"
        assert "secret123" not in caplog.text

    def test_error_field_when_provided(self, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.mcp_access"):
            log_mcp_tool_call("update", {}, None, latency_ms=0, error="Claim not found")
        entry = json.loads(caplog.records[-1].message)
        assert entry["error"] == "Claim not found"

    def test_no_resp_key_when_none(self, caplog):
        with caplog.at_level(logging.INFO, logger="dejaship.mcp_access"):
            log_mcp_tool_call("update", {}, None, latency_ms=0, error="fail")
        entry = json.loads(caplog.records[-1].message)
        assert "resp" not in entry
