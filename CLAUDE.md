# DejaShip Development Guide

## Project Structure

Monorepo with two packages:
- `backend/` - Python FastAPI server (REST API + MCP endpoint)
- `mcp-client/` - TypeScript MCP stdio client (npx wrapper)

## Quick Start

```bash
# Start pgvector + backend
docker compose up --build

# Run migrations
cd backend && uv run alembic upgrade head

# Run tests (requires Docker for testcontainers)
cd backend && uv run pytest tests/ -v
```

## Backend Commands

```bash
cd backend
uv sync --all-extras     # Install all deps
uv run uvicorn dejaship.main:app --reload  # Dev server
uv run alembic upgrade head                # Run migrations
uv run alembic revision --autogenerate -m "description"  # New migration
uv run pytest tests/ -v                    # Run tests
uv run python scripts/abandon_stale.py     # Cleanup stale claims
```

## MCP Client Commands

```bash
cd mcp-client
npm install && npm run build   # Build
node build/index.js            # Run locally
```

## Architecture

- REST endpoints at `/v1/check`, `/v1/claim`, `/v1/update`
- MCP Streamable HTTP at `/mcp`
- Both REST and MCP call shared `services.py`
- Embeddings via fastembed (ONNX, configurable model)
- `embed_text()` is CPU-bound — services.py offloads it via `run_in_threadpool`
- Rate limiting: SlowAPI 60/min per IP, Cloudflare-aware (`limiter.py`)
- pgvector for vector similarity search (HNSW index, m=16, ef_construction=64)

## Gotchas

- **Never call `embed_text()` directly in async context** — it blocks the event loop.
  It's always wrapped in `run_in_threadpool` inside `services.py`. Keep it that way.
- **Tests need Docker running** — testcontainers spins up a real pgvector container.
- **Rate limits in tests**: SlowAPI limits share in-memory state per IP key
  (`"testclient"` for all test requests). 60/min is safe for the current suite but
  watch if tests grow significantly.
- **rulesync**: `GEMINI.md`, `AGENTS.md`, `.agent/rules/claude.md`, etc. are generated.
  Edit `.rulesync/rules/CLAUDE.md`, then run `rulesync generate`.

## Environment Variables

All prefixed with `DEJASHIP_`. See `.env.example` for full list.
Key: `DATABASE_URL`, `EMBEDDING_MODEL`, `SIMILARITY_THRESHOLD`.

Experiment flags (all default to off):
- `EMBEDDING_INCLUDE_CORE_MECHANIC` — toggle core_mechanic in embedding text
- `ENABLE_JACCARD_FILTER`, `ENABLE_TWO_STAGE_RETRIEVAL`, `ENABLE_CROSS_ENCODER`, etc.

## Search Quality

Current state (2026-03-02, coverage-max corpus):
- FPR: 0.72, recall: 0.73, exact_top1: 1.0, balanced_score: 2.36
- Main blocker: generic SaaS vocabulary inflates cross-domain similarity

Key docs:
- `docs/search-quality/false-positive-root-cause.md` — why FPR is 72%
- `docs/search-quality/improvement-approaches.md` — 11 ranked solutions with config flags
- `docs/search-quality/model-comparison.md` — fastembed 768-dim model analysis
- `docs/decisions/2026-03-02-embedding-text-strategy.md` — keywords-only experiment & revert
- `docs/agent-sim-coverage-max-status.md` — measured quality metrics & next steps
- `docs/plans/2026-03-02-search-quality-improvement-plan.md` — implementation plan

Evaluation commands:
```bash
cd backend
uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval --model-set coverage-max
uv run python -m tests.agent_sim.tools.evaluate_similarity_thresholds --model-set coverage-max
uv run python -m tests.agent_sim.tools.run_quality_suite --scenario smoke --model-set coverage-max
```

## Rules Sync (multi-agent)

```bash
rulesync generate                      # Regenerate all tool configs from .rulesync/rules/
rulesync install                       # Re-fetch pinned skills from sources
rulesync import --targets claudecode   # Re-import CLAUDE.md into .rulesync/
```

Source of truth: `.rulesync/rules/CLAUDE.md` → `GEMINI.md`, `AGENTS.md`, `.agent/`, `.cursor/`, etc.

## Conventions

- Python: async everywhere, SQLAlchemy 2.0 style, Pydantic for validation
- Tests: integration tests with real pgvector via testcontainers
- Commits: conventional commits (feat/fix/docs/refactor)
- CI: GitHub Actions runs `pytest` on push/PR to `main`/`dev`
