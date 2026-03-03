# DejaShip MVP Design

**Date:** 2026-03-01
**Status:** Approved

---

## 1. Architecture Overview

DejaShip is a monorepo with two packages:

```
dejaship/
├── backend/          # Python FastAPI (ONNX embeddings, pgvector, MCP endpoint)
├── mcp-client/       # TypeScript thin stdio wrapper (npx distribution)
├── docker-compose.yml
├── LICENSE           # MIT (single license for MVP)
└── doc/
```

### Runtime Architecture

```
Agent (Claude, Devin, etc.)
    │
    ├── Direct: Streamable HTTP ──→ api.dejaship.com/mcp ──→ FastAPI
    │                                                         ├── fastembed (ONNX, in-process)
    │                                                         └── pgvector (PostgreSQL)
    │
    └── Via npx: stdio ──→ dejaship-mcp (local) ──→ HTTPS ──→ api.dejaship.com/v1/*
                           (thin HTTP wrapper)
```

### Key Decisions

- **Single process** - FastAPI serves both REST (`/v1/*`) and MCP (`/mcp`) endpoints
- **Model baked into Docker image** - `BAAI/bge-base-en-v1.5` downloaded at build time, loaded at startup
- **Guest token pattern** - No auth for check/claim, `edit_token` returned on claim for updates
- **Docker Compose** for local dev (FastAPI + pgvector)
- **Cloudflare Tunnel** for production ingress
- **MIT license** for entire repo during MVP

---

## 2. Backend Package Structure

```
backend/
├── pyproject.toml              # uv project, dependencies
├── Dockerfile
├── alembic/                    # DB migrations
│   ├── alembic.ini
│   └── versions/
├── scripts/
│   └── download_model.py       # Run during Docker build to bake model
├── tests/
│   ├── conftest.py             # Docker pgvector fixture
│   └── test_api.py             # Integration tests for all 3 endpoints
└── src/
    └── dejaship/
        ├── __init__.py
        ├── main.py             # FastAPI app, lifespan, route mounting
        ├── config.py           # Settings via pydantic-settings
        ├── db.py               # SQLAlchemy async engine, session factory
        ├── models.py           # SQLAlchemy ORM: AgentIntent table
        ├── schemas.py          # Pydantic request/response models
        ├── embeddings.py       # fastembed wrapper (configurable model)
        ├── services.py         # Core business logic (shared by REST + MCP)
        ├── api/
        │   ├── __init__.py
        │   ├── check.py        # POST /v1/check
        │   ├── claim.py        # POST /v1/claim
        │   └── update.py       # POST /v1/update
        └── mcp/
            ├── __init__.py
            └── server.py       # FastMCP Streamable HTTP, 3 tools
```

---

## 3. Database Schema

```sql
CREATE TYPE intent_status AS ENUM ('in_progress', 'shipped', 'abandoned');

CREATE TABLE agent_intents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    core_mechanic   TEXT NOT NULL,
    keywords        JSONB NOT NULL,
    embedding       vector(768) NOT NULL,
    status          intent_status NOT NULL DEFAULT 'in_progress',
    edit_token_hash TEXT NOT NULL,
    resolution_url  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_intents_embedding ON agent_intents
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_intents_status ON agent_intents (status);
```

- **HNSW index** over IVFFlat - better recall at low data volumes, no retraining needed.
- **Cosine similarity** (`vector_cosine_ops`) - matches `bge-base-en-v1.5` training.
- **`edit_token_hash`** - `sha256(token)`, never the raw token. Compared via `hmac.compare_digest`.

---

## 4. Embedding Pipeline

```
Input: { core_mechanic: "seo tool for plumbers", keywords: ["seo", "plumber", "local-business", ...] }
                │
                ▼
Weighted concatenation:
  - First 10 keywords repeated 2x (dominant signal)
  - Remaining keywords included 1x
  - core_mechanic appended 1x (supporting context)
                │
                ▼
fastembed.TextEmbedding(model_name=settings.EMBEDDING_MODEL)
                │
                ▼
768-dim vector → stored in pgvector
```

Keywords are the primary signal. Core mechanic provides freeform context.
Repeating the first 10 keywords shifts the embedding toward keyword semantics.

### Default Model: `BAAI/bge-base-en-v1.5`

- 110M params, ~210MB ONNX, 768 dimensions
- Strong on short-text similarity (STS: 82.4 on MTEB)
- Fast CPU inference via ONNX runtime
- Model name is configurable via `EMBEDDING_MODEL` env var

---

## 5. API Endpoints

### `POST /v1/check`

**Input:**
```json
{
  "core_mechanic": "string (1-250 chars)",
  "keywords": ["string (3-40 chars)", ...] // 5+ items
}
```

**Output:**
```json
{
  "neighborhood_density": {
    "in_progress": 2,
    "shipped": 0,
    "abandoned": 12
  },
  "closest_active_claims": [
    {"mechanic": "...", "status": "in_progress", "age_hours": 14}
  ]
}
```

Read-only. Embeds input, searches pgvector by cosine similarity (threshold 0.75), groups by status.

### `POST /v1/claim`

**Input:** Same as `/check`.

**Output:**
```json
{
  "claim_id": "uuid-v4",
  "edit_token": "secure-random-string",
  "status": "in_progress",
  "timestamp": "ISO-8601"
}
```

Creates record, returns raw `edit_token` (stored hashed).

### `POST /v1/update`

**Input:**
```json
{
  "claim_id": "uuid-v4",
  "edit_token": "secure-random-string",
  "status": "shipped | abandoned",
  "resolution_url": "string (optional)"
}
```

**Output:** `{ "success": true }`

Validates token hash (constant-time), transitions state. Cannot go back to `in_progress`.

---

## 6. MCP Tools

3 tools exposed via FastMCP Streamable HTTP at `/mcp`:

| Tool Name | Maps To | Annotations |
|-----------|---------|-------------|
| `dejaship_check_airspace` | `services.check_airspace` | `readOnlyHint: true` |
| `dejaship_claim_intent` | `services.claim_intent` | `readOnlyHint: false` |
| `dejaship_update_claim` | `services.update_claim` | `readOnlyHint: false` |

Both REST and MCP call the same `services.py` functions. No duplication.

---

## 7. Configuration

All settings via environment variables (`pydantic-settings`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://dejaship:dejaship@localhost:5432/dejaship` | Async PostgreSQL URL |
| `EMBEDDING_MODEL` | `BAAI/bge-base-en-v1.5` | fastembed model name |
| `VECTOR_DIMENSIONS` | `768` | Embedding vector size |
| `SIMILARITY_THRESHOLD` | `0.75` | Cosine similarity cutoff |
| `MAX_CLOSEST_RESULTS` | `10` | Max results in closest_active_claims |
| `KEYWORD_REPEAT` | `2` | Times to repeat first 10 keywords |
| `MIN_KEYWORDS` | `5` | Minimum keywords required |
| `KEYWORD_MIN_LENGTH` | `3` | Min chars per keyword |
| `KEYWORD_MAX_LENGTH` | `40` | Max chars per keyword |
| `CORE_MECHANIC_MAX_LENGTH` | `250` | Max chars for core_mechanic |
| `ABANDONMENT_DAYS` | `7` | Days before implicit abandonment |

---

## 8. TypeScript MCP Client

```
mcp-client/
├── package.json          # "dejaship-mcp", bin entry
├── tsconfig.json
└── src/
    └── index.ts          # ~100 lines, stdio-to-HTTP bridge
```

- Registers same 3 tools, each `fetch()`es `/v1/*` on `api.dejaship.com`
- Config: `DEJASHIP_API_URL` env var (default: `https://api.dejaship.com`)
- Published to npm as `dejaship-mcp`
- Agent config: `{ "command": "npx", "args": ["-y", "dejaship-mcp"] }`

---

## 9. Docker & Infrastructure

### Docker Compose (local dev)

```yaml
services:
  db:
    image: pgvector/pgvector:pg17
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: dejaship
      POSTGRES_USER: dejaship
      POSTGRES_PASSWORD: dejaship
    volumes:
      - pgdata:/var/lib/postgresql/data

  backend:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://dejaship:dejaship@db:5432/dejaship
      EMBEDDING_MODEL: BAAI/bge-base-en-v1.5
    depends_on: [db]

volumes:
  pgdata:
```

### Backend Dockerfile (multi-stage)

```dockerfile
# Stage 1: Download model at build time
FROM python:3.12-slim AS model
RUN pip install fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-base-en-v1.5')"

# Stage 2: Runtime
FROM python:3.12-slim
COPY --from=model /root/.cache/fastembed /root/.cache/fastembed
# install deps via uv, copy source, etc.
```

### Production

```
┌─── Host Machine ──────────────────────────────┐
│  docker compose -f docker-compose.prod.yml up  │
│    ├── backend (FastAPI :8000)                  │
│    ├── db (pgvector :5432)                     │
│    └── cloudflared (tunnel)                    │
│         └── routes api.dejaship.com → :8000    │
└────────────────────────────────────────────────┘
```

### Stale Claim Cleanup

`scripts/abandon_stale.py` runs as cron:
```sql
UPDATE agent_intents SET status='abandoned', updated_at=now()
WHERE status='in_progress' AND updated_at < now() - interval '7 days';
```

---

## 10. Integration Tests

Using `pytest` + `httpx.AsyncClient` + `testcontainers-python` (pgvector).

| Test | Validates |
|------|-----------|
| `test_check_empty_db` | Zero density on fresh database |
| `test_claim_returns_token` | Creates record, returns claim_id + edit_token |
| `test_check_finds_similar` | Claim "seo tool for plumbers", check "seo for local plumbing" → density > 0 |
| `test_check_ignores_dissimilar` | Claim "seo tool", check "knitting inventory" → density = 0 |
| `test_update_shipped` | Update to shipped with URL |
| `test_update_abandoned` | Update to abandoned |
| `test_update_wrong_token` | Wrong edit_token → 403 |
| `test_update_invalid_transition` | Abandoned → in_progress → 400 |
| `test_keyword_validation` | Reject < 5 keywords, wrong length |
| `test_mcp_endpoint` | Streamable HTTP at /mcp responds |

---

## 11. Implementation Order

1. **Phase 1: Foundation** - backend skeleton, config, DB, embeddings, Docker
2. **Phase 2: API** - services.py, 3 REST endpoints, FastAPI app
3. **Phase 3: MCP** - FastMCP server, mount into app
4. **Phase 4: Tests** - testcontainers setup, integration tests
5. **Phase 5: TS Client** - mcp-client package, npx wrapper
6. **Phase 6: Infrastructure** - stale cleanup, cloudflared, .env.example
