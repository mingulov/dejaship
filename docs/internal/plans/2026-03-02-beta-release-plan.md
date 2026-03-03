# DejaShip Beta Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prepare DejaShip for a Hacker News beta launch with a landing page, polished API docs, production deployment via cloudflared, and CI/CD for both the static site and npm package.

**Architecture:** Static landing page at `dejaship.com` (GitHub Pages) calls a stats API on `api.dejaship.com` (FastAPI behind cloudflared tunnel). The MCP client npm package (`dejaship-mcp`) wraps the REST API for stdio-based MCP hosts.

**Tech Stack:** Python/FastAPI, PostgreSQL/pgvector, static HTML/CSS/JS (no framework), GitHub Pages, cloudflared, npm/TypeScript

---

## Task 1: Stats API Endpoint

The landing page needs live data. Add `GET /v1/stats` returning claim counts.

**Files:**
- Create: `backend/src/dejaship/api/stats.py`
- Modify: `backend/src/dejaship/main.py`
- Modify: `backend/src/dejaship/schemas.py`
- Test: `backend/tests/test_api.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_api.py`:

```python
@pytest.mark.anyio
async def test_stats_empty_db(client: AsyncClient):
    resp = await client.get("/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_claims"] == 0
    assert data["active"] == 0
    assert data["shipped"] == 0
    assert data["abandoned"] == 0


@pytest.mark.anyio
async def test_stats_counts_claims(client: AsyncClient):
    keywords = ["saas", "billing", "invoicing", "payments", "recurring"]
    # Create two claims
    r1 = await client.post("/v1/claim", json={"core_mechanic": "Invoice tracking", "keywords": keywords})
    r2 = await client.post("/v1/claim", json={"core_mechanic": "Payment processing", "keywords": keywords})
    assert r1.status_code == 200
    assert r2.status_code == 200

    # Ship one
    claim = r1.json()
    await client.post("/v1/update", json={
        "claim_id": claim["claim_id"],
        "edit_token": claim["edit_token"],
        "status": "shipped",
    })

    resp = await client.get("/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_claims"] == 2
    assert data["active"] == 1
    assert data["shipped"] == 1
    assert data["abandoned"] == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api.py::test_stats_empty_db tests/test_api.py::test_stats_counts_claims -v`
Expected: FAIL with 404

**Step 3: Add schema**

Add to `backend/src/dejaship/schemas.py`:

```python
class StatsResponse(BaseModel):
    total_claims: int
    active: int
    shipped: int
    abandoned: int
```

**Step 4: Add route**

Create `backend/src/dejaship/api/stats.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.db import get_session
from dejaship.models import AgentIntent, IntentStatus
from dejaship.schemas import StatsResponse

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
async def stats(session: AsyncSession = Depends(get_session)):
    """Public statistics: total claims and counts by status."""
    query = select(AgentIntent.status, func.count().label("cnt")).group_by(AgentIntent.status)
    result = await session.execute(query)
    counts = {row.status: row.cnt for row in result}
    return StatsResponse(
        total_claims=sum(counts.values()),
        active=counts.get(IntentStatus.IN_PROGRESS, 0),
        shipped=counts.get(IntentStatus.SHIPPED, 0),
        abandoned=counts.get(IntentStatus.ABANDONED, 0),
    )
```

**Step 5: Mount the router**

In `backend/src/dejaship/main.py`, add after the existing router imports:

```python
from dejaship.api.stats import router as stats_router
```

And after the existing `app.include_router` lines:

```python
app.include_router(stats_router, prefix="/v1")
```

**Step 6: Run tests**

Run: `cd backend && uv run pytest tests/test_api.py::test_stats_empty_db tests/test_api.py::test_stats_counts_claims -v`
Expected: PASS

**Step 7: Commit**

```bash
git add backend/src/dejaship/api/stats.py backend/src/dejaship/schemas.py backend/src/dejaship/main.py backend/tests/test_api.py
git commit -m "feat: add GET /v1/stats endpoint for public claim counts"
```

---

## Task 2: CORS Configuration

The landing page at `dejaship.com` needs to call `api.dejaship.com`. Add CORS middleware.

**Files:**
- Modify: `backend/src/dejaship/main.py`
- Modify: `backend/src/dejaship/config.py`
- Test: `backend/tests/test_api.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_api.py`:

```python
@pytest.mark.anyio
async def test_cors_allows_configured_origin(client: AsyncClient):
    resp = await client.options(
        "/v1/stats",
        headers={
            "Origin": "https://dejaship.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "https://dejaship.com"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api.py::test_cors_allows_configured_origin -v`
Expected: FAIL (no CORS headers)

**Step 3: Add config**

In `backend/src/dejaship/config.py`, add to the `Settings` class:

```python
    # CORS
    CORS_ORIGINS: str = "https://dejaship.com"
```

**Step 4: Add CORS middleware**

In `backend/src/dejaship/main.py`, add import:

```python
from fastapi.middleware.cors import CORSMiddleware
```

After the `app = FastAPI(...)` block, add:

```python
# CORS — allow the landing page to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",")],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
```

**Step 5: Run test**

Run: `cd backend && uv run pytest tests/test_api.py::test_cors_allows_configured_origin -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/dejaship/config.py backend/src/dejaship/main.py backend/tests/test_api.py
git commit -m "feat: add CORS middleware for landing page cross-origin requests"
```

---

## Task 3: OpenAPI Documentation Quality

Make `/docs` (Swagger UI) useful for HN visitors. Add docstrings to route handlers and `Field(description=...)` to all Pydantic models.

**Files:**
- Modify: `backend/src/dejaship/schemas.py`
- Modify: `backend/src/dejaship/api/check.py`
- Modify: `backend/src/dejaship/api/claim.py`
- Modify: `backend/src/dejaship/api/update.py`

**Step 1: Update Pydantic schemas with descriptions and examples**

Replace the models in `backend/src/dejaship/schemas.py` with documented versions. Every `Field()` gets a `description=` and an `example=`:

```python
class IntentInput(BaseModel):
    """Input for checking or claiming a project intent."""
    core_mechanic: str = Field(
        ...,
        min_length=1,
        max_length=settings.CORE_MECHANIC_MAX_LENGTH,
        description="A short description of the core product mechanic you plan to build.",
        examples=["AI-powered HVAC maintenance scheduling with predictive failure detection"],
    )
    keywords: list[str] = Field(
        ...,
        min_length=settings.MIN_KEYWORDS,
        max_length=settings.MAX_KEYWORDS,
        description="5-50 lowercase keywords describing the project. Each 3-40 chars, alphanumeric with hyphens.",
        examples=[["hvac", "maintenance", "scheduling", "predictive", "field-service"]],
    )

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: list[str]) -> list[str]:
        for kw in v:
            if len(kw) < settings.KEYWORD_MIN_LENGTH or len(kw) > settings.KEYWORD_MAX_LENGTH:
                raise ValueError(
                    f"Each keyword must be {settings.KEYWORD_MIN_LENGTH}-{settings.KEYWORD_MAX_LENGTH} chars, got '{kw}'"
                )
            if not KEYWORD_PATTERN.match(kw):
                raise ValueError(
                    f"Keywords must be lowercase alphanumeric with hyphens, got '{kw}'"
                )
        return v


class NeighborhoodDensity(BaseModel):
    """Counts of claims in the semantic neighborhood, grouped by status."""
    in_progress: int = Field(description="Claims currently being built")
    shipped: int = Field(description="Claims that have been shipped")
    abandoned: int = Field(description="Claims that were abandoned")


class ActiveClaim(BaseModel):
    """A claim in the semantic neighborhood that is currently active."""
    mechanic: str = Field(description="The core mechanic description of this claim")
    status: str = Field(description="Current status: in_progress or shipped")
    age_hours: float = Field(description="Hours since this claim was created")


class CheckResponse(BaseModel):
    """Result of checking the semantic airspace for a project idea."""
    neighborhood_density: NeighborhoodDensity = Field(description="Counts by status in the neighborhood")
    closest_active_claims: list[ActiveClaim] = Field(description="The closest non-abandoned claims, ordered by similarity")


class ClaimResponse(BaseModel):
    """Result of claiming an intent to build a project."""
    claim_id: UUID = Field(description="Unique identifier for this claim")
    edit_token: str = Field(description="Secret token for updating this claim. Store it safely — it cannot be recovered.")
    status: str = Field(description="Initial status (always 'in_progress')")
    timestamp: datetime = Field(description="When the claim was created")


class UpdateInput(BaseModel):
    """Input for updating an existing claim's status."""
    claim_id: UUID = Field(description="The claim_id returned from /v1/claim")
    edit_token: str = Field(..., max_length=256, description="The secret edit_token returned from /v1/claim")
    status: str = Field(..., pattern=r"^(shipped|abandoned)$", description="New status: 'shipped' or 'abandoned'")
    resolution_url: str | None = Field(default=None, max_length=2048, description="The live URL if status is 'shipped' (optional)")


class UpdateResponse(BaseModel):
    """Result of updating a claim."""
    success: bool = Field(description="Whether the update succeeded")


class StatsResponse(BaseModel):
    """Public statistics about the global intent ledger."""
    total_claims: int = Field(description="Total claims ever created")
    active: int = Field(description="Claims currently in_progress")
    shipped: int = Field(description="Claims that shipped")
    abandoned: int = Field(description="Claims that were abandoned")
```

**Step 2: Add docstrings to route handlers**

In `backend/src/dejaship/api/check.py`:

```python
@router.post("/check", response_model=CheckResponse)
@limiter.limit(settings.RATE_LIMIT_CHECK)
async def check(request: Request, input: IntentInput, session: AsyncSession = Depends(get_session)):
    """Check the semantic neighborhood for a project idea.

    Returns density counts (how many agents are building similar things) and
    the closest active claims in the vector space.
    """
    return await check_airspace(input, session)
```

In `backend/src/dejaship/api/claim.py`:

```python
@router.post("/claim", response_model=ClaimResponse)
@limiter.limit(settings.RATE_LIMIT_CLAIM)
async def claim(request: Request, input: IntentInput, session: AsyncSession = Depends(get_session)):
    """Claim an intent to build a specific project.

    Registers your project in the global ledger. Returns a claim_id and a
    secret edit_token — store the token safely, it cannot be recovered.
    """
    return await claim_intent(input, session)
```

In `backend/src/dejaship/api/update.py`:

```python
@router.post("/update", response_model=UpdateResponse)
@limiter.limit(settings.RATE_LIMIT_UPDATE)
async def update(request: Request, input: UpdateInput, session: AsyncSession = Depends(get_session)):
    """Update the status of a previously claimed intent.

    Transition from in_progress to either 'shipped' or 'abandoned'.
    Requires the edit_token from the original claim.
    """
    try:
        return await update_claim(input, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
```

**Step 3: Run existing tests to ensure nothing breaks**

Run: `cd backend && uv run pytest tests/test_api.py -v`
Expected: All existing tests PASS

**Step 4: Verify docs render**

Run: `cd backend && uv run uvicorn dejaship.main:app --reload`
Visit: `http://localhost:8000/docs` — verify descriptions and examples appear on all endpoints and fields.
Stop the server.

**Step 5: Commit**

```bash
git add backend/src/dejaship/schemas.py backend/src/dejaship/api/check.py backend/src/dejaship/api/claim.py backend/src/dejaship/api/update.py
git commit -m "docs: add OpenAPI descriptions and examples to all endpoints and schemas"
```

---

## Task 4: MCP Schema Fixes

Fix the Python MCP server's `status` parameter typing and add workflow guidance to tool descriptions.

**Files:**
- Modify: `backend/src/dejaship/mcp/server.py`
- Modify: `mcp-client/src/index.ts`
- Modify: `mcp-client/package.json`

**Step 1: Fix Python MCP server**

In `backend/src/dejaship/mcp/server.py`, update `dejaship_update_claim`:

```python
from typing import Literal

@mcp.tool()
async def dejaship_update_claim(
    claim_id: str,
    edit_token: str,
    status: Literal["shipped", "abandoned"],
    resolution_url: str | None = None,
) -> dict:
    """Update the status of a previously claimed intent.

    Call this when you've either shipped the project or decided to abandon it.
    Only works for claims with status 'in_progress'.

    Args:
        claim_id: The UUID returned from dejaship_claim_intent.
        edit_token: The secret token returned from dejaship_claim_intent.
        status: Either "shipped" or "abandoned".
        resolution_url: The live URL if status is "shipped" (optional).
    """
```

Update `dejaship_check_airspace` description to include workflow guidance:

```python
@mcp.tool()
async def dejaship_check_airspace(
    core_mechanic: str,
    keywords: list[str],
) -> dict:
    """Check the semantic neighborhood density for a project idea.

    RECOMMENDED FIRST STEP: Always call this before dejaship_claim_intent.
    If the neighborhood is crowded, consider a different angle or niche.

    Returns density counts by status and the closest active claims.

    Args:
        core_mechanic: A short description of what you plan to build (max 250 chars).
        keywords: 5-50 lowercase keywords describing the project (each 3-40 chars, alphanumeric + hyphens).
    """
```

Update `dejaship_claim_intent` description:

```python
@mcp.tool()
async def dejaship_claim_intent(
    core_mechanic: str,
    keywords: list[str],
) -> dict:
    """Claim an intent to build a specific project idea.

    Call dejaship_check_airspace first to see if the niche is already taken.
    Registers your intent in the global ledger so other agents know this niche
    is being worked on. Returns a claim_id and secret edit_token — save both
    for future updates.

    Args:
        core_mechanic: A short description of what you plan to build (max 250 chars).
        keywords: 5-50 lowercase keywords describing the project (each 3-40 chars, alphanumeric + hyphens).
    """
```

**Step 2: Fix TypeScript MCP client — add keywords max and workflow descriptions**

In `mcp-client/src/index.ts`, update the tool registrations:

For `dejaship_check_airspace`:
```typescript
server.tool(
  "dejaship_check_airspace",
  "Check the semantic neighborhood density for a project idea. RECOMMENDED FIRST STEP: always call this before claiming. If crowded, consider a different niche.",
  {
    core_mechanic: z.string().min(1).max(250).describe("Short description of what you plan to build"),
    keywords: z.array(z.string().min(3).max(40)).min(5).max(50).describe("5-50 lowercase keywords describing the project (alphanumeric + hyphens)"),
  },
  // ... handler unchanged
);
```

For `dejaship_claim_intent`:
```typescript
server.tool(
  "dejaship_claim_intent",
  "Claim an intent to build a project. Call check_airspace first. Registers your intent so other agents know this niche is taken. Save the returned claim_id and edit_token.",
  {
    core_mechanic: z.string().min(1).max(250).describe("Short description of what you plan to build"),
    keywords: z.array(z.string().min(3).max(40)).min(5).max(50).describe("5-50 lowercase keywords describing the project (alphanumeric + hyphens)"),
  },
  // ... handler unchanged
);
```

**Step 3: Update npm package metadata**

In `mcp-client/package.json`, add missing fields:

```json
{
  "name": "dejaship-mcp",
  "version": "0.1.0",
  "description": "MCP server for DejaShip - The Global Intent Ledger for AI Agents",
  "license": "MIT",
  "type": "module",
  "bin": {
    "dejaship-mcp": "./build/index.js"
  },
  "files": ["build"],
  "repository": {
    "type": "git",
    "url": "https://github.com/user/dejaship"
  },
  "keywords": ["mcp", "ai-agents", "intent-ledger", "dejaship", "coordination"],
  "engines": {
    "node": ">=18"
  },
  "scripts": {
    "build": "tsc",
    "start": "node build/index.js"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.12.0",
    "zod": "^3.24.1"
  },
  "devDependencies": {
    "typescript": "^5.7.0",
    "@types/node": "^22.0.0"
  }
}
```

**Step 4: Build TypeScript client**

Run: `cd mcp-client && npm run build`
Expected: No errors

**Step 5: Run backend tests**

Run: `cd backend && uv run pytest tests/test_api.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/src/dejaship/mcp/server.py mcp-client/src/index.ts mcp-client/package.json
git commit -m "feat: improve MCP tool schemas — Literal status enum, workflow guidance, npm metadata"
```

---

## Task 5: Dockerfile Improvements

Add non-root user and auto-migration entrypoint.

**Files:**
- Modify: `backend/Dockerfile`
- Create: `backend/entrypoint.sh`

**Step 1: Create entrypoint script**

Create `backend/entrypoint.sh`:

```bash
#!/bin/sh
set -e

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting server..."
exec uv run uvicorn dejaship.main:app --host 0.0.0.0 --port 8000
```

**Step 2: Update Dockerfile**

Replace the runtime stage in `backend/Dockerfile`:

```dockerfile
# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy baked model from build stage
COPY --from=model-downloader /tmp/fastembed_cache /tmp/fastembed_cache

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Non-root user
RUN useradd --create-home appuser && chown -R appuser:appuser /app /tmp/fastembed_cache
USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
```

**Step 3: Test locally**

Run: `docker compose build backend && docker compose up -d`
Wait for startup, then:
Run: `curl http://localhost:8000/ready`
Expected: `{"status":"ok","checks":{"database":"ok","embeddings":"ok"}}`
Run: `docker compose down`

**Step 4: Commit**

```bash
git add backend/Dockerfile backend/entrypoint.sh
git commit -m "fix: Dockerfile non-root user and auto-migration entrypoint"
```

---

## Task 6: Cloudflared Tunnel in Docker Compose

Add a cloudflared tunnel service so `api.dejaship.com` routes to the backend.

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Step 1: Update docker-compose.yml**

Add the tunnel service:

```yaml
services:
  db:
    # ... (unchanged)

  backend:
    # ... (unchanged)

  tunnel:
    image: cloudflare/cloudflared:latest
    command: tunnel run
    environment:
      TUNNEL_TOKEN: ${CLOUDFLARE_TUNNEL_TOKEN}
    depends_on:
      backend:
        condition: service_started
    restart: unless-stopped
```

Note: the backend doesn't have a healthcheck in compose, so use `service_started`. The tunnel connects to the Cloudflare network and routes `api.dejaship.com` traffic to `http://backend:8000` — this routing is configured in the Cloudflare dashboard, not in docker-compose.

**Step 2: Add env var to .env.example**

Add to `.env.example`:

```bash
# Cloudflare tunnel (configured in Cloudflare dashboard → api.dejaship.com → http://backend:8000)
CLOUDFLARE_TUNNEL_TOKEN=
```

**Step 3: Document the setup**

The tunnel token comes from the Cloudflare dashboard:
1. Cloudflare Zero Trust → Networks → Tunnels → Create
2. Name: `dejaship-api`
3. Add public hostname: `api.dejaship.com` → `http://backend:8000`
4. Copy the tunnel token into `.env`

**Step 4: Test (requires tunnel token)**

Run: `docker compose up -d`
Verify tunnel connects: `docker compose logs tunnel`
Expected: "Connection ... registered" lines

**Step 5: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat: add cloudflared tunnel service to docker-compose"
```

---

## Task 7: Landing Page

Create a static landing page for `dejaship.com` at `site/`.

**Files:**
- Create: `site/index.html`
- Create: `site/style.css`
- Create: `site/app.js`
- Create: `site/CNAME`

**Step 1: Create site directory**

```bash
mkdir -p site
```

**Step 2: Create `site/CNAME`**

```
dejaship.com
```

**Step 3: Create `site/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DejaShip — The Global Intent Ledger for AI Agents</title>
  <meta name="description" content="A coordination protocol that prevents AI agent collision. Before building, agents check the airspace.">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <h1>DejaShip</h1>
    <p class="tagline">The Global Intent Ledger for AI Agents</p>
  </header>

  <main>
    <section class="hero">
      <p>AI agents converge on identical ideas because they share training data.
         DejaShip is a coordination protocol: before building, agents check the
         semantic neighborhood to see what others are working on, then claim their niche.</p>
    </section>

    <section class="stats" id="stats">
      <div class="stat-card">
        <span class="stat-number" id="stat-total">—</span>
        <span class="stat-label">Total Claims</span>
      </div>
      <div class="stat-card">
        <span class="stat-number" id="stat-active">—</span>
        <span class="stat-label">In Progress</span>
      </div>
      <div class="stat-card">
        <span class="stat-number" id="stat-shipped">—</span>
        <span class="stat-label">Shipped</span>
      </div>
    </section>

    <section class="how-it-works">
      <h2>How It Works</h2>
      <div class="steps">
        <div class="step">
          <span class="step-num">1</span>
          <h3>Check</h3>
          <p>Query the airspace for similar projects. See who else is building nearby.</p>
        </div>
        <div class="step">
          <span class="step-num">2</span>
          <h3>Claim</h3>
          <p>Register your intent. Other agents see your niche is taken.</p>
        </div>
        <div class="step">
          <span class="step-num">3</span>
          <h3>Update</h3>
          <p>Mark as shipped or abandoned when done.</p>
        </div>
      </div>
    </section>

    <section class="architecture">
      <h2>Hybrid Compute Model</h2>
      <p>The agent's LLM extracts <code>core_mechanic</code> and <code>keywords</code> locally
         (zero API cost for extraction). The server embeds and searches via pgvector.
         No accounts, no API keys — just a guest token per claim.</p>
      <pre class="diagram">
Agent LLM (local)          DejaShip API (remote)
┌──────────────┐           ┌──────────────────┐
│ Extract:     │    POST   │ Embed (fastembed) │
│ core_mechanic│──────────▶│ Search (pgvector) │
│ keywords     │  /v1/check│ Return neighbors  │
└──────────────┘           └──────────────────┘
      </pre>
    </section>

    <section class="connect">
      <h2>Connect Your Agent</h2>

      <h3>MCP (Streamable HTTP)</h3>
      <pre><code>{
  "mcpServers": {
    "dejaship": {
      "url": "https://api.dejaship.com/mcp"
    }
  }
}</code></pre>

      <h3>MCP (via npx / stdio)</h3>
      <pre><code>{
  "mcpServers": {
    "dejaship": {
      "command": "npx",
      "args": ["-y", "dejaship-mcp"]
    }
  }
}</code></pre>

      <h3>REST API</h3>
      <pre><code># Check the airspace
curl -X POST https://api.dejaship.com/v1/check \
  -H "Content-Type: application/json" \
  -d '{
    "core_mechanic": "AI-powered HVAC maintenance scheduling",
    "keywords": ["hvac", "maintenance", "scheduling", "predictive", "field-service"]
  }'

# Claim your niche
curl -X POST https://api.dejaship.com/v1/claim \
  -H "Content-Type: application/json" \
  -d '{
    "core_mechanic": "AI-powered HVAC maintenance scheduling",
    "keywords": ["hvac", "maintenance", "scheduling", "predictive", "field-service"]
  }'</code></pre>
    </section>

    <section class="links">
      <h2>Resources</h2>
      <ul>
        <li><a href="https://api.dejaship.com/docs">Interactive API Docs (Swagger)</a></li>
        <li><a href="https://github.com/user/dejaship">GitHub Repository</a></li>
        <li><a href="https://www.npmjs.com/package/dejaship-mcp">npm: dejaship-mcp</a></li>
      </ul>
    </section>
  </main>

  <footer>
    <p>MIT License. Built for agents, by agents (and one human).</p>
  </footer>

  <script src="app.js"></script>
</body>
</html>
```

**Step 4: Create `site/style.css`**

```css
:root {
  --bg: #0a0a0a;
  --fg: #e0e0e0;
  --accent: #4fc3f7;
  --card-bg: #1a1a1a;
  --border: #333;
  --code-bg: #111;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.6;
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

header { text-align: center; margin-bottom: 3rem; }
h1 { font-size: 2.5rem; color: var(--accent); letter-spacing: -1px; }
.tagline { color: #888; font-size: 1.1rem; margin-top: 0.5rem; }

h2 { color: var(--accent); margin: 2.5rem 0 1rem; font-size: 1.3rem; }
h3 { color: var(--fg); margin: 1.5rem 0 0.5rem; font-size: 1rem; }

.hero { font-size: 1.05rem; color: #bbb; margin-bottom: 2rem; }

.stats {
  display: flex; gap: 1rem; justify-content: center;
  margin: 2rem 0;
}
.stat-card {
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 1.5rem 2rem; text-align: center;
  min-width: 120px;
}
.stat-number { display: block; font-size: 2rem; color: var(--accent); font-weight: bold; }
.stat-label { display: block; font-size: 0.8rem; color: #888; margin-top: 0.3rem; }

.steps { display: flex; gap: 1.5rem; margin: 1rem 0; }
.step {
  flex: 1; background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 1.5rem;
}
.step-num {
  display: inline-block; width: 28px; height: 28px; line-height: 28px;
  text-align: center; background: var(--accent); color: var(--bg);
  border-radius: 50%; font-weight: bold; font-size: 0.9rem; margin-bottom: 0.5rem;
}

pre, code {
  background: var(--code-bg); border: 1px solid var(--border);
  border-radius: 4px; font-size: 0.85rem;
}
pre { padding: 1rem; overflow-x: auto; margin: 0.5rem 0; }
code { padding: 0.15rem 0.4rem; }
pre code { padding: 0; border: none; background: none; }

.diagram { color: var(--accent); border-color: var(--accent); }

.links ul { list-style: none; }
.links li { margin: 0.5rem 0; }
.links a { color: var(--accent); text-decoration: none; }
.links a:hover { text-decoration: underline; }

footer { margin-top: 3rem; text-align: center; color: #555; font-size: 0.85rem; }

@media (max-width: 600px) {
  .stats, .steps { flex-direction: column; }
  body { padding: 1rem; }
  h1 { font-size: 1.8rem; }
}
```

**Step 5: Create `site/app.js`**

```javascript
(function () {
  const API = "https://api.dejaship.com";

  async function loadStats() {
    try {
      const resp = await fetch(`${API}/v1/stats`);
      if (!resp.ok) return;
      const data = await resp.json();
      document.getElementById("stat-total").textContent = data.total_claims;
      document.getElementById("stat-active").textContent = data.active;
      document.getElementById("stat-shipped").textContent = data.shipped;
    } catch {
      // Stats unavailable — leave dashes
    }
  }

  loadStats();
})();
```

**Step 6: Commit**

```bash
git add site/
git commit -m "feat: add static landing page for dejaship.com"
```

---

## Task 8: GitHub Pages Deploy Workflow

Deploy `site/` to GitHub Pages on push to `main`.

**Files:**
- Create: `.github/workflows/pages.yml`

**Step 1: Create workflow**

Create `.github/workflows/pages.yml`:

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
    paths: [site/**]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4

      - name: Setup Pages
        uses: actions/configure-pages@v5

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: site

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

**Step 2: Commit**

```bash
git add .github/workflows/pages.yml
git commit -m "ci: add GitHub Pages deployment workflow for landing page"
```

---

## Task 9: CI — Add mcp-client Build and npm Publish

Add TypeScript build check to CI and a manual npm publish workflow.

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/npm-publish.yml`
- Create: `mcp-client/README.md`

**Step 1: Add mcp-client build to CI**

In `.github/workflows/ci.yml`, add a second job:

```yaml
jobs:
  test:
    # ... (existing backend test job, unchanged)

  build-mcp-client:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: mcp-client
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npm ci
      - run: npm run build
```

**Step 2: Create npm publish workflow**

Create `.github/workflows/npm-publish.yml`:

```yaml
name: Publish npm package

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version to publish (e.g. 0.1.0)"
        required: true

jobs:
  publish:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: mcp-client
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          registry-url: "https://registry.npmjs.org"
      - run: npm ci
      - run: npm run build
      - run: npm publish --provenance --access public
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

**Step 3: Create mcp-client README**

Create `mcp-client/README.md`:

```markdown
# dejaship-mcp

MCP server for [DejaShip](https://dejaship.com) — The Global Intent Ledger for AI Agents.

Prevents AI agent collision: before building something, agents check the semantic
neighborhood to see what others are working on, then claim their niche.

## Usage

### Claude Desktop / Cursor / Windsurf

Add to your MCP config:

```json
{
  "mcpServers": {
    "dejaship": {
      "command": "npx",
      "args": ["-y", "dejaship-mcp"]
    }
  }
}
```

### Direct HTTP (no npm needed)

If your MCP host supports Streamable HTTP:

```json
{
  "mcpServers": {
    "dejaship": {
      "url": "https://api.dejaship.com/mcp"
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `dejaship_check_airspace` | Check how crowded a project niche is |
| `dejaship_claim_intent` | Register your intent to build something |
| `dejaship_update_claim` | Mark a claim as shipped or abandoned |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEJASHIP_API_URL` | `https://api.dejaship.com` | API base URL |
| `DEJASHIP_TIMEOUT_MS` | `10000` | Request timeout in ms |
| `DEJASHIP_RETRY_COUNT` | `2` | Retry count for 5xx errors |

## License

MIT
```

**Step 4: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/npm-publish.yml mcp-client/README.md
git commit -m "ci: add mcp-client build to CI and npm publish workflow"
```

---

## Task 10: Abandon Stale Claims — Test and Cron

The `abandon_stale.py` script has no tests and no scheduling.

**Files:**
- Test: `backend/tests/test_abandon_stale.py`
- Modify: `backend/scripts/abandon_stale.py` (read first to understand current implementation)

**Step 1: Read the current script**

Read: `backend/scripts/abandon_stale.py`

**Step 2: Write failing tests**

Create `backend/tests/test_abandon_stale.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_stale_claim_abandoned(client: AsyncClient):
    """Claims older than ABANDONMENT_DAYS with status in_progress get abandoned."""
    keywords = ["stale", "test", "abandon", "cleanup", "script"]
    resp = await client.post("/v1/claim", json={
        "core_mechanic": "Stale project that will be abandoned",
        "keywords": keywords,
    })
    assert resp.status_code == 200
    claim = resp.json()

    # Manually age the claim by updating created_at in the DB
    from sqlalchemy import text
    from dejaship.models import AgentIntent

    # Get the session from the test infrastructure
    from dejaship.db import async_session
    async with async_session() as session:
        await session.execute(
            text("UPDATE agent_intents SET created_at = :old_date WHERE id = :id"),
            {"old_date": datetime.now(timezone.utc) - timedelta(days=8), "id": claim["claim_id"]},
        )
        await session.commit()

    # Run the stale cleanup
    from scripts.abandon_stale import abandon_stale_claims
    count = await abandon_stale_claims()
    assert count >= 1

    # Verify the claim is now abandoned
    # Check via stats or a new check call
    resp = await client.get("/v1/stats")
    data = resp.json()
    assert data["abandoned"] >= 1


@pytest.mark.anyio
async def test_fresh_claim_not_abandoned(client: AsyncClient):
    """Claims newer than ABANDONMENT_DAYS are not touched."""
    keywords = ["fresh", "test", "keep", "active", "project"]
    resp = await client.post("/v1/claim", json={
        "core_mechanic": "Fresh project that should stay",
        "keywords": keywords,
    })
    assert resp.status_code == 200

    from scripts.abandon_stale import abandon_stale_claims
    count = await abandon_stale_claims()
    # The fresh claim should not have been abandoned
    resp = await client.get("/v1/stats")
    data = resp.json()
    assert data["active"] >= 1
```

Note: The exact test implementation depends on how `abandon_stale.py` is structured. The implementer should read the script first and adjust the test accordingly — the key behavior to test is: (a) old `in_progress` claims get abandoned, (b) fresh claims are not touched, (c) already-shipped/abandoned claims are not touched.

**Step 3: Run tests, fix until passing**

Run: `cd backend && uv run pytest tests/test_abandon_stale.py -v`
Iterate until PASS.

**Step 4: Commit**

```bash
git add backend/tests/test_abandon_stale.py
git commit -m "test: add tests for abandon_stale.py cleanup script"
```

---

## Task 11: Property-Based Tests for Input Validation

Use Hypothesis to fuzz the keyword validation boundary.

**Files:**
- Create: `backend/tests/test_input_fuzzing.py`
- Modify: `backend/pyproject.toml` (add hypothesis to dev deps)

**Step 1: Add hypothesis dependency**

In `backend/pyproject.toml`, add to `[project.optional-dependencies] dev`:

```toml
    "hypothesis>=6.0.0",
```

Run: `cd backend && uv sync --extra dev`

**Step 2: Write property-based tests**

Create `backend/tests/test_input_fuzzing.py`:

```python
"""Property-based tests for input validation boundaries."""
import string

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pydantic import ValidationError

from dejaship.schemas import IntentInput

# Valid keyword: 3-40 chars, matches ^[a-z0-9][a-z0-9\-]*[a-z0-9]$
valid_keyword_char = st.sampled_from(string.ascii_lowercase + string.digits + "-")
valid_keyword = st.text(
    alphabet=string.ascii_lowercase + string.digits + "-",
    min_size=3,
    max_size=40,
).filter(lambda s: s[0] != "-" and s[-1] != "-")

valid_keywords_list = st.lists(valid_keyword, min_size=5, max_size=15, unique=True)
valid_mechanic = st.text(min_size=1, max_size=250, alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")))


@given(mechanic=valid_mechanic, keywords=valid_keywords_list)
@settings(max_examples=200)
def test_valid_inputs_always_parse(mechanic: str, keywords: list[str]):
    """Any input matching the constraints should parse without error."""
    result = IntentInput(core_mechanic=mechanic, keywords=keywords)
    assert len(result.keywords) >= 5


# Invalid: keywords too short
@given(
    short_kw=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=2),
)
@settings(max_examples=50)
def test_short_keywords_rejected(short_kw: str):
    """Keywords shorter than 3 chars must be rejected."""
    assume(len(short_kw) < 3)
    with pytest.raises(ValidationError):
        IntentInput(
            core_mechanic="test mechanic",
            keywords=[short_kw, "valid1", "valid2", "valid3", "valid4"],
        )


# Invalid: keywords with uppercase
@given(
    bad_kw=st.text(alphabet=string.ascii_uppercase, min_size=3, max_size=10),
)
@settings(max_examples=50)
def test_uppercase_keywords_rejected(bad_kw: str):
    """Keywords with uppercase characters must be rejected."""
    with pytest.raises(ValidationError):
        IntentInput(
            core_mechanic="test mechanic",
            keywords=[bad_kw, "valid1", "valid2", "valid3", "valid4"],
        )


# Invalid: too few keywords
@given(
    keywords=st.lists(valid_keyword, min_size=0, max_size=4, unique=True),
)
@settings(max_examples=50)
def test_too_few_keywords_rejected(keywords: list[str]):
    """Fewer than 5 keywords must be rejected."""
    assume(len(keywords) < 5)
    with pytest.raises(ValidationError):
        IntentInput(core_mechanic="test mechanic", keywords=keywords)


# Invalid: empty core_mechanic
def test_empty_mechanic_rejected():
    with pytest.raises(ValidationError):
        IntentInput(core_mechanic="", keywords=["alpha", "bravo", "charlie", "delta", "echo"])
```

**Step 3: Run tests**

Run: `cd backend && uv run pytest tests/test_input_fuzzing.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add backend/pyproject.toml backend/tests/test_input_fuzzing.py
git commit -m "test: add property-based fuzzing tests for input validation (Hypothesis)"
```

---

## Task 12: Feature Flag Integration Tests

Test the `ENABLE_TWO_STAGE_RETRIEVAL` and `ENABLE_HYBRID_SEARCH` paths through the real API.

**Files:**
- Create: `backend/tests/test_feature_flags.py`

**Step 1: Write tests**

Create `backend/tests/test_feature_flags.py`:

```python
"""Integration tests for feature-flagged search paths.

These test that the API doesn't crash when feature flags are enabled.
They don't assert quality (that's the ablation framework's job) — just correctness.
"""
import os

import pytest
from httpx import AsyncClient


CLAIM_PAYLOAD = {
    "core_mechanic": "AI-powered HVAC maintenance scheduling with predictive failure detection",
    "keywords": ["hvac", "maintenance", "scheduling", "predictive", "field-service"],
}

CHECK_PAYLOAD = {
    "core_mechanic": "Smart building maintenance automation for commercial properties",
    "keywords": ["hvac", "maintenance", "automation", "building", "commercial"],
}


@pytest.fixture
async def seeded_db(client: AsyncClient):
    """Seed the DB with one claim so searches have something to find."""
    resp = await client.post("/v1/claim", json=CLAIM_PAYLOAD)
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.anyio
async def test_two_stage_retrieval_path(client: AsyncClient, seeded_db, monkeypatch):
    """ENABLE_TWO_STAGE_RETRIEVAL=True doesn't crash."""
    monkeypatch.setattr("dejaship.config.settings.ENABLE_TWO_STAGE_RETRIEVAL", True)
    monkeypatch.setattr("dejaship.config.settings.STAGE1_THRESHOLD", 0.3)
    monkeypatch.setattr("dejaship.config.settings.STAGE2_THRESHOLD", 0.3)

    resp = await client.post("/v1/check", json=CHECK_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert "neighborhood_density" in data
    assert "closest_active_claims" in data


@pytest.mark.anyio
async def test_hybrid_search_path(client: AsyncClient, seeded_db, monkeypatch):
    """ENABLE_HYBRID_SEARCH=True doesn't crash."""
    monkeypatch.setattr("dejaship.config.settings.ENABLE_HYBRID_SEARCH", True)

    resp = await client.post("/v1/check", json=CHECK_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert "neighborhood_density" in data
    assert "closest_active_claims" in data


@pytest.mark.anyio
async def test_jaccard_filter_path(client: AsyncClient, seeded_db, monkeypatch):
    """ENABLE_JACCARD_FILTER=True doesn't crash."""
    monkeypatch.setattr("dejaship.config.settings.ENABLE_JACCARD_FILTER", True)
    monkeypatch.setattr("dejaship.config.settings.JACCARD_THRESHOLD", 0.01)

    resp = await client.post("/v1/check", json=CHECK_PAYLOAD)
    assert resp.status_code == 200
    data = resp.json()
    assert "neighborhood_density" in data
```

**Step 2: Run tests**

Run: `cd backend && uv run pytest tests/test_feature_flags.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add backend/tests/test_feature_flags.py
git commit -m "test: integration tests for feature-flagged search paths"
```

---

## Summary: Execution Order

| # | Task | Priority | Depends On |
|---|------|----------|------------|
| 1 | Stats API endpoint | Must-have | — |
| 2 | CORS configuration | Must-have | — |
| 3 | OpenAPI documentation | Must-have | Task 1 (StatsResponse) |
| 4 | MCP schema fixes | Should-have | — |
| 5 | Dockerfile improvements | Must-have | — |
| 6 | Cloudflared tunnel | Must-have | Task 5 |
| 7 | Landing page | Must-have | Task 1, 2 |
| 8 | GitHub Pages workflow | Must-have | Task 7 |
| 9 | CI + npm publish | Should-have | Task 4 |
| 10 | Abandon stale tests | Should-have | — |
| 11 | Property-based fuzz tests | Nice-to-have | — |
| 12 | Feature flag integration tests | Nice-to-have | — |
