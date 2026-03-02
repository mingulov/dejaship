"""Regression tests for MCP protocol compliance.

These tests verify that the Python FastMCP server exposes correct
instructions, tool annotations, field descriptions, and structured
error responses — as seen by MCP clients on the wire.

No Docker required — these introspect the FastMCP server object directly.
"""
import json

import pytest
from pydantic import ValidationError

from dejaship.mcp.server import mcp, _validation_error_response


# ---------------------------------------------------------------------------
# Server-level instructions
# ---------------------------------------------------------------------------

class TestServerInstructions:
    """Server MUST expose instructions so agents understand the workflow."""

    def test_instructions_is_set(self):
        assert mcp.instructions is not None

    def test_instructions_is_nonempty_string(self):
        assert isinstance(mcp.instructions, str)
        assert len(mcp.instructions) > 0

    def test_instructions_mentions_workflow_order(self):
        inst = mcp.instructions
        assert "check_airspace" in inst
        assert "claim_intent" in inst
        assert "update_claim" in inst

    def test_instructions_mentions_edit_token(self):
        assert "edit_token" in mcp.instructions

    def test_instructions_mentions_claim_id(self):
        assert "claim_id" in mcp.instructions


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    """All 3 tools must be registered with correct names."""

    def _tool_names(self) -> list[str]:
        return [t.name for t in mcp._tool_manager.list_tools()]

    def test_three_tools_registered(self):
        assert len(self._tool_names()) == 3

    def test_check_airspace_registered(self):
        assert "dejaship_check_airspace" in self._tool_names()

    def test_claim_intent_registered(self):
        assert "dejaship_claim_intent" in self._tool_names()

    def test_update_claim_registered(self):
        assert "dejaship_update_claim" in self._tool_names()


# ---------------------------------------------------------------------------
# Tool annotations
# ---------------------------------------------------------------------------

def _get_tool(name: str):
    for t in mcp._tool_manager.list_tools():
        if t.name == name:
            return t
    raise ValueError(f"Tool {name} not found")


class TestCheckAirspaceAnnotations:
    def test_annotations_not_none(self):
        tool = _get_tool("dejaship_check_airspace")
        assert tool.annotations is not None

    def test_read_only_hint(self):
        tool = _get_tool("dejaship_check_airspace")
        assert tool.annotations.readOnlyHint is True

    def test_destructive_hint(self):
        tool = _get_tool("dejaship_check_airspace")
        assert tool.annotations.destructiveHint is False

    def test_idempotent_hint(self):
        tool = _get_tool("dejaship_check_airspace")
        assert tool.annotations.idempotentHint is True

    def test_open_world_hint(self):
        tool = _get_tool("dejaship_check_airspace")
        assert tool.annotations.openWorldHint is True


class TestClaimIntentAnnotations:
    def test_annotations_not_none(self):
        tool = _get_tool("dejaship_claim_intent")
        assert tool.annotations is not None

    def test_read_only_hint(self):
        tool = _get_tool("dejaship_claim_intent")
        assert tool.annotations.readOnlyHint is False

    def test_destructive_hint(self):
        tool = _get_tool("dejaship_claim_intent")
        assert tool.annotations.destructiveHint is False

    def test_idempotent_hint(self):
        tool = _get_tool("dejaship_claim_intent")
        assert tool.annotations.idempotentHint is False

    def test_open_world_hint(self):
        tool = _get_tool("dejaship_claim_intent")
        assert tool.annotations.openWorldHint is True


class TestUpdateClaimAnnotations:
    def test_annotations_not_none(self):
        tool = _get_tool("dejaship_update_claim")
        assert tool.annotations is not None

    def test_read_only_hint(self):
        tool = _get_tool("dejaship_update_claim")
        assert tool.annotations.readOnlyHint is False

    def test_destructive_hint(self):
        tool = _get_tool("dejaship_update_claim")
        assert tool.annotations.destructiveHint is True

    def test_idempotent_hint(self):
        tool = _get_tool("dejaship_update_claim")
        assert tool.annotations.idempotentHint is False

    def test_open_world_hint(self):
        tool = _get_tool("dejaship_update_claim")
        assert tool.annotations.openWorldHint is True


# ---------------------------------------------------------------------------
# Field descriptions in JSON Schema
# ---------------------------------------------------------------------------

def _get_schema_props(tool_name: str) -> dict:
    tool = _get_tool(tool_name)
    return tool.parameters.get("properties", {})


class TestCheckAirspaceSchema:
    def test_core_mechanic_has_description(self):
        props = _get_schema_props("dejaship_check_airspace")
        assert "description" in props["core_mechanic"]

    def test_keywords_has_description(self):
        props = _get_schema_props("dejaship_check_airspace")
        assert "description" in props["keywords"]

    def test_core_mechanic_has_example(self):
        desc = _get_schema_props("dejaship_check_airspace")["core_mechanic"]["description"]
        assert "example" in desc.lower() or "Example" in desc

    def test_keywords_mentions_normalization(self):
        desc = _get_schema_props("dejaship_check_airspace")["keywords"]["description"]
        assert "normalize" in desc.lower() or "lowercase" in desc.lower()


class TestUpdateClaimSchema:
    """The status field MUST have a description (Literal types don't auto-generate one)."""

    def test_status_has_description(self):
        props = _get_schema_props("dejaship_update_claim")
        assert "description" in props["status"]

    def test_status_description_mentions_shipped(self):
        desc = _get_schema_props("dejaship_update_claim")["status"]["description"]
        assert "shipped" in desc.lower()

    def test_status_description_mentions_abandoned(self):
        desc = _get_schema_props("dejaship_update_claim")["status"]["description"]
        assert "abandoned" in desc.lower()

    def test_status_description_mentions_final(self):
        desc = _get_schema_props("dejaship_update_claim")["status"]["description"]
        assert "final" in desc.lower() or "FINAL" in desc

    def test_resolution_url_has_description(self):
        props = _get_schema_props("dejaship_update_claim")
        assert "description" in props["resolution_url"]

    def test_claim_id_has_description(self):
        props = _get_schema_props("dejaship_update_claim")
        assert "description" in props["claim_id"]

    def test_edit_token_has_description(self):
        props = _get_schema_props("dejaship_update_claim")
        assert "description" in props["edit_token"]


# ---------------------------------------------------------------------------
# Structured validation error responses
# ---------------------------------------------------------------------------

class TestValidationErrorResponse:
    """MCP tools return structured errors, not raw Pydantic tracebacks."""

    def _trigger_validation_error(self) -> ValidationError:
        from dejaship.schemas import IntentInput
        try:
            IntentInput(core_mechanic="", keywords=[])
        except ValidationError as e:
            return e
        raise AssertionError("Expected ValidationError")

    def test_error_response_has_error_key(self):
        e = self._trigger_validation_error()
        resp = _validation_error_response(e)
        assert resp["error"] == "validation_failed"

    def test_error_response_has_issues_list(self):
        e = self._trigger_validation_error()
        resp = _validation_error_response(e)
        assert isinstance(resp["issues"], list)
        assert len(resp["issues"]) > 0

    def test_error_response_has_hint(self):
        e = self._trigger_validation_error()
        resp = _validation_error_response(e)
        assert "hint" in resp
        assert isinstance(resp["hint"], str)

    def test_error_response_has_example(self):
        e = self._trigger_validation_error()
        resp = _validation_error_response(e)
        assert "example" in resp
        assert "core_mechanic" in resp["example"]
        assert "keywords" in resp["example"]

    def test_error_response_is_json_serializable(self):
        e = self._trigger_validation_error()
        resp = _validation_error_response(e)
        # Must not raise
        json.dumps(resp)


# ---------------------------------------------------------------------------
# Keyword normalization through MCP path
# ---------------------------------------------------------------------------

class TestKeywordNormalizationMCPPath:
    """Keywords sent via MCP are normalized by IntentInput before services."""

    def test_uppercase_normalized(self):
        from dejaship.schemas import IntentInput
        inp = IntentInput(
            core_mechanic="test",
            keywords=["HELLO", "WORLD", "testing", "alpha", "bravo"],
        )
        assert inp.keywords == ["hello", "world", "testing", "alpha", "bravo"]

    def test_spaces_to_hyphens(self):
        from dejaship.schemas import IntentInput
        inp = IntentInput(
            core_mechanic="test",
            keywords=["hello world", "foo bar", "testing", "alpha", "bravo"],
        )
        assert "hello-world" in inp.keywords
        assert "foo-bar" in inp.keywords

    def test_special_chars_stripped(self):
        from dejaship.schemas import IntentInput
        inp = IntentInput(
            core_mechanic="test",
            keywords=["hello!", "world@#", "test$ing", "alpha", "bravo"],
        )
        assert "hello" in inp.keywords
        assert "world" in inp.keywords
        assert "testing" in inp.keywords

    def test_too_short_after_normalization_rejected(self):
        from dejaship.schemas import IntentInput
        with pytest.raises(ValidationError):
            IntentInput(
                core_mechanic="test",
                keywords=["!!", "automation", "freelance", "stripe", "payments"],
            )

    def test_structured_error_for_bad_keywords(self):
        """When MCP tool catches ValidationError, it returns structured response."""
        from dejaship.schemas import IntentInput
        try:
            IntentInput(
                core_mechanic="test",
                keywords=["!!", "automation", "freelance", "stripe", "payments"],
            )
        except ValidationError as e:
            resp = _validation_error_response(e)
            assert resp["error"] == "validation_failed"
            assert any("too short" in issue for issue in resp["issues"])


class TestOutputSchemas:
    """Tools must declare output schemas so agents know the response shape."""

    def test_check_airspace_has_output_schema(self):
        tool = _get_tool("dejaship_check_airspace")
        assert tool.output_schema is not None

    def test_check_airspace_output_has_neighborhood_density(self):
        tool = _get_tool("dejaship_check_airspace")
        props = tool.output_schema.get("properties", {})
        assert "neighborhood_density" in props

    def test_check_airspace_output_has_closest_active_claims(self):
        tool = _get_tool("dejaship_check_airspace")
        props = tool.output_schema.get("properties", {})
        assert "closest_active_claims" in props

    def test_claim_intent_has_output_schema(self):
        tool = _get_tool("dejaship_claim_intent")
        assert tool.output_schema is not None

    def test_claim_intent_output_has_claim_id(self):
        tool = _get_tool("dejaship_claim_intent")
        props = tool.output_schema.get("properties", {})
        assert "claim_id" in props

    def test_claim_intent_output_has_edit_token(self):
        tool = _get_tool("dejaship_claim_intent")
        props = tool.output_schema.get("properties", {})
        assert "edit_token" in props

    def test_update_claim_has_output_schema(self):
        tool = _get_tool("dejaship_update_claim")
        assert tool.output_schema is not None

    def test_update_claim_output_has_success(self):
        tool = _get_tool("dejaship_update_claim")
        props = tool.output_schema.get("properties", {})
        assert "success" in props
