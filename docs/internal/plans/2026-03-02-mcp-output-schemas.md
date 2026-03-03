# MCP Output Schemas & Quality Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add output schemas, openWorldHint, and error guidance to both MCP servers so agents know exactly what every tool returns.

**Architecture:** Python FastMCP uses `structured_output=True` with existing Pydantic response models as return types. TypeScript client migrates from deprecated `server.tool()` to `server.registerTool()` with Zod output schemas. Both servers add `openWorldHint: true` to all tool annotations.

**Tech Stack:** Python FastMCP 1.26 (`structured_output=True`), TypeScript MCP SDK 1.12 (`registerTool` + `outputSchema`), Zod schemas.

---

### Task 1: Python — Add openWorldHint to all tool annotations

**Files:**
- Modify: `backend/src/dejaship/mcp/server.py`
- Test: `backend/tests/test_mcp_protocol.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_mcp_protocol.py` in each annotation test class:

```python
# In TestCheckAirspaceAnnotations:
def test_open_world_hint(self):
    tool = _get_tool("dejaship_check_airspace")
    assert tool.annotations.openWorldHint is True

# In TestClaimIntentAnnotations:
def test_open_world_hint(self):
    tool = _get_tool("dejaship_claim_intent")
    assert tool.annotations.openWorldHint is True

# In TestUpdateClaimAnnotations:
def test_open_world_hint(self):
    tool = _get_tool("dejaship_update_claim")
    assert tool.annotations.openWorldHint is True
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_mcp_protocol.py::TestCheckAirspaceAnnotations::test_open_world_hint tests/test_mcp_protocol.py::TestClaimIntentAnnotations::test_open_world_hint tests/test_mcp_protocol.py::TestUpdateClaimAnnotations::test_open_world_hint -v`
Expected: FAIL — `openWorldHint` is currently `None`

**Step 3: Add openWorldHint to all 3 tool annotations**

In `backend/src/dejaship/mcp/server.py`, update each `@mcp.tool(annotations=ToolAnnotations(...))` to include `openWorldHint=True`:

```python
# check_airspace
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))

# claim_intent
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))

# update_claim
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True))
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_mcp_protocol.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/dejaship/mcp/server.py backend/tests/test_mcp_protocol.py
git commit -m "feat: add openWorldHint=True to all MCP tool annotations"
```

---

### Task 2: Python — Add output schemas via structured_output

**Files:**
- Modify: `backend/src/dejaship/mcp/server.py`
- Test: `backend/tests/test_mcp_protocol.py`

**Step 1: Write the failing tests**

Add a new test class to `backend/tests/test_mcp_protocol.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_mcp_protocol.py::TestOutputSchemas -v`
Expected: FAIL — `output_schema` is `None` on all tools

**Step 3: Change return types from `dict` to Pydantic models**

In `backend/src/dejaship/mcp/server.py`:

1. Update imports (add `CheckResponse`, `ClaimResponse`, `UpdateResponse`):

```python
from dejaship.schemas import IntentInput, UpdateInput, CheckResponse, ClaimResponse, UpdateResponse
```

2. Update `dejaship_check_airspace`:

Change the decorator to add `structured_output=True` and the return type from `-> dict` to `-> CheckResponse`:

```python
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True), structured_output=True)
async def dejaship_check_airspace(
    ...
) -> CheckResponse:
```

Change the return line from `return result.model_dump()` to `return result` (the service already returns a `CheckResponse`).

Keep the error path returning `_validation_error_response(e)` as dict — FastMCP handles mixed return types.

3. Update `dejaship_claim_intent`:

```python
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True), structured_output=True)
async def dejaship_claim_intent(
    ...
) -> ClaimResponse:
```

Change `return result.model_dump(mode="json")` to `return result`.

4. Update `dejaship_update_claim`:

```python
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True), structured_output=True)
async def dejaship_update_claim(
    ...
) -> UpdateResponse:
```

Change `return result.model_dump()` to `return result`.
Keep the error paths returning dict.

**Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_mcp_protocol.py -v`
Expected: ALL PASS

Then run the full integration test suite to catch regressions:

Run: `cd backend && uv run pytest tests/test_api.py -v` (if Docker is available)

**Step 5: Commit**

```bash
git add backend/src/dejaship/mcp/server.py backend/tests/test_mcp_protocol.py
git commit -m "feat: add output schemas to all MCP tools via structured_output"
```

---

### Task 3: TypeScript — Migrate to registerTool with outputSchema and openWorldHint

**Files:**
- Modify: `mcp-client/src/index.ts`

**Step 1: Migrate `dejaship_check_airspace` from `server.tool()` to `server.registerTool()`**

Replace:

```typescript
server.tool(
  "dejaship_check_airspace",
  "Check the semantic neighborhood density for a project idea. RECOMMENDED FIRST STEP: always call this before claiming. If crowded, consider a different niche.",
  {
    core_mechanic: z.string().min(1).max(250).describe(...),
    keywords: z.array(...).min(5).max(50).describe(...),
  },
  { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
  async ({ core_mechanic, keywords }) => {
    const result = await apiCall("check", { core_mechanic, keywords });
    return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
  }
);
```

With:

```typescript
server.registerTool("dejaship_check_airspace", {
  description:
    "Check the semantic neighborhood density for a project idea. RECOMMENDED FIRST STEP: always call this before claiming. If crowded, consider a different niche.",
  inputSchema: {
    core_mechanic: z.string().min(1).max(250).describe(
      "Short, specific description of what you plan to build. Be concrete about the core value proposition. " +
      "Example: 'AI-powered invoice automation for freelancers'"
    ),
    keywords: z.array(z.string().min(3).max(40)).min(5).max(50).describe(
      "5-50 keywords describing the project. Auto-normalized by the server: uppercase converted to lowercase, " +
      "spaces converted to hyphens. Use domain terms, tech stack, and target market. " +
      "Example: ['invoicing', 'automation', 'freelance', 'stripe', 'payments']"
    ),
  },
  outputSchema: {
    neighborhood_density: z.object({
      in_progress: z.number().describe("Claims currently being built"),
      shipped: z.number().describe("Claims that have been shipped"),
      abandoned: z.number().describe("Claims that were abandoned"),
    }).describe("Counts by status in the neighborhood"),
    closest_active_claims: z.array(z.object({
      mechanic: z.string().describe("Core mechanic description of this claim"),
      status: z.string().describe("Current status: in_progress or shipped"),
      age_hours: z.number().describe("Hours since this claim was created"),
    })).describe("Closest non-abandoned claims, ordered by similarity"),
  },
  annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
}, async ({ core_mechanic, keywords }) => {
  const result = await apiCall("check", { core_mechanic, keywords }) as Record<string, unknown>;
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    structuredContent: result,
  };
});
```

**Step 2: Migrate `dejaship_claim_intent`**

```typescript
server.registerTool("dejaship_claim_intent", {
  description:
    "Claim an intent to build a project. Call check_airspace first. Registers your intent so other agents know this niche is taken. Save the returned claim_id and edit_token.",
  inputSchema: {
    core_mechanic: z.string().min(1).max(250).describe(
      "Short, specific description of what you plan to build. Be concrete about the core value proposition. " +
      "Example: 'AI-powered invoice automation for freelancers'"
    ),
    keywords: z.array(z.string().min(3).max(40)).min(5).max(50).describe(
      "5-50 keywords describing the project. Auto-normalized by the server: uppercase converted to lowercase, " +
      "spaces converted to hyphens. Use domain terms, tech stack, and target market. " +
      "Example: ['invoicing', 'automation', 'freelance', 'stripe', 'payments']"
    ),
  },
  outputSchema: {
    claim_id: z.string().uuid().describe("Unique identifier for this claim — save this"),
    edit_token: z.string().describe("Secret token for updating this claim — save this, it cannot be recovered"),
    status: z.string().describe("Initial status (always 'in_progress')"),
    timestamp: z.string().describe("When the claim was created (ISO 8601)"),
  },
  annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
}, async ({ core_mechanic, keywords }) => {
  const result = await apiCall("claim", { core_mechanic, keywords }) as Record<string, unknown>;
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    structuredContent: result,
  };
});
```

**Step 3: Migrate `dejaship_update_claim`**

```typescript
server.registerTool("dejaship_update_claim", {
  description:
    "Update a claimed intent to 'shipped' or 'abandoned'. FINAL — cannot be undone. Only works for in_progress claims. Use resolution_url when shipping. " +
    "Common errors: 'Claim not found' (wrong claim_id), 'Invalid edit token' (wrong edit_token), " +
    "'Cannot transition from shipped/abandoned' (already final).",
  inputSchema: {
    claim_id: z.string().uuid().describe("The claim_id from dejaship_claim_intent"),
    edit_token: z.string().describe("The secret edit_token from dejaship_claim_intent"),
    status: z.enum(["shipped", "abandoned"]).describe(
      "'shipped' = project is live (include resolution_url). 'abandoned' = stopped working on it. FINAL."
    ),
    resolution_url: z.string().url().optional().describe(
      "Live URL of the shipped project. Strongly recommended when status is 'shipped'."
    ),
  },
  outputSchema: {
    success: z.boolean().describe("Whether the update succeeded"),
  },
  annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true },
}, async ({ claim_id, edit_token, status, resolution_url }) => {
  const result = await apiCall("update", { claim_id, edit_token, status, resolution_url }) as Record<string, unknown>;
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    structuredContent: result,
  };
});
```

**Step 4: Build and verify wire output**

Run:
```bash
cd mcp-client && npm run build
```

Then verify wire output:
```bash
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n' | timeout 5 node build/index.js 2>/dev/null
```

Verify in output:
- All 3 tools have `outputSchema` objects (not null/undefined)
- All 3 tools have `openWorldHint: true` in annotations
- `update_claim` description includes common errors

**Step 5: Commit**

```bash
git add mcp-client/src/index.ts
git commit -m "feat: migrate to registerTool with outputSchema and openWorldHint"
```

---

### Task 4: Add error guidance to TypeScript update_claim description

Already done in Task 3 — the `update_claim` description now includes:
> "Common errors: 'Claim not found' (wrong claim_id), 'Invalid edit token' (wrong edit_token), 'Cannot transition from shipped/abandoned' (already final)."

No separate task needed.

---

### Task 5: Update CLAUDE.md with new MCP conventions

**Files:**
- Modify: `.rulesync/rules/CLAUDE.md`

**Step 1: Add to MCP Server Requirements section**

Under the existing "Python FastMCP" sub-section, add:

```markdown
- Use `structured_output=True` + Pydantic return types for output schemas: `@mcp.tool(structured_output=True)` + `-> CheckResponse:`
- Error paths can return `dict` even when return type is Pydantic — FastMCP handles mixed returns
```

Under the existing "TypeScript MCP client" sub-section, add:

```markdown
- Use `server.registerTool(name, config, callback)` (not deprecated `server.tool()`)
- `config.outputSchema` takes Zod shapes, `callback` returns `{ content, structuredContent }`
```

**Step 2: Run rulesync**

```bash
cd /home/user/src/m/dejaship/dejaship && rulesync generate
```

**Step 3: Commit**

```bash
git add .rulesync/rules/CLAUDE.md CLAUDE.md
git commit -m "docs: add outputSchema and registerTool conventions to CLAUDE.md"
```
