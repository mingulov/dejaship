"""Tests for HTTP request/response access logging middleware."""

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from dejaship.access_log import access_log_middleware


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

    return app


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
