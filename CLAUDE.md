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
- `filters.py` — Jaccard keyword filter + optional spaCy lemmatization
- `reranker.py` — ColBERT MaxSim reranker (LateInteractionTextEmbedding)
- `fts.py` — Reciprocal Rank Fusion for hybrid vector + FTS search
- Embeddings via fastembed (ONNX, configurable model)
- `embed_text()` is CPU-bound — services.py offloads it via `run_in_threadpool`
- Rate limiting: SlowAPI 60/min per IP, Cloudflare-aware (`limiter.py`)
- pgvector for vector similarity search (HNSW index, m=16, ef_construction=64)

## MCP Server Requirements

**Python FastMCP** (`backend/src/dejaship/mcp/server.py`):
- Always add `ToolAnnotations` to every tool: `from mcp.types import ToolAnnotations`, then `@mcp.tool(annotations=ToolAnnotations(readOnlyHint=..., destructiveHint=..., idempotentHint=...))`
- `FastMCP("name", instructions="...", ...)` — `instructions` is a first-class kwarg; without it `mcp.instructions = None` and agents get no server overview
- `Literal["a", "b"]` type hints generate **no description** in JSON Schema — must use `Annotated[Literal["a", "b"], Field(description="...")]`
- Inspect live schema without running the server: `mcp._tool_manager.list_tools()` → `.parameters`, `.annotations`, `.description`; check `mcp.instructions`
- Use `structured_output=True` + Pydantic return types for output schemas: `@mcp.tool(structured_output=True)` + `-> CheckResponse:` — FastMCP auto-generates `outputSchema` from the return annotation
- Error paths can return `dict` even when return type annotation is a Pydantic model — FastMCP handles mixed returns correctly

**TypeScript MCP client** (`mcp-client/src/index.ts`):
- `new McpServer(serverInfo, { instructions: "..." })` — instructions goes in the second arg options object
- `server.tool(name, description, schema, annotations, callback)` — annotations `{readOnlyHint, destructiveHint, idempotentHint}` is the 4th positional arg
- Inspect live wire output: `printf 'msg1\nmsg2\n' | node build/index.js 2>/dev/null`
- Use `server.registerTool(name, config, callback)` not deprecated `server.tool()` — `registerTool` supports `outputSchema`
- `config.outputSchema` takes Zod shapes (same as `inputSchema`); callback returns `{ content: [...], structuredContent: result }`
- `openWorldHint: true` in annotations for tools that call external APIs or interact with external data

**Verification** — always verify wire output, not just source code:
- TypeScript: send real MCP messages via stdio and parse JSON responses
- Python: `mcp._tool_manager.list_tools()` → check `.annotations` (must not be `None`) and `.parameters` for field descriptions

## Gotchas

- **Pyright `reportMissingImports`** for `dejaship.*`, `fastembed`, `sqlalchemy` etc. are false
  positives — Pyright doesn't see the uv venv. All tests pass regardless.
- **`keywords` column is JSONB** — use `jsonb_array_elements_text(keywords)` in raw SQL,
  NOT `array_to_string(keywords, ' ')` (that's for native PostgreSQL ARRAYs, not JSONB).
- **fastembed**: `TextCrossEncoder` does NOT exist. Use `LateInteractionTextEmbedding` for
  reranking. Available models: `colbert-ir/colbertv2.0`, `answerdotai/answerai-colbert-small-v1`.
- **NLP extras**: `uv sync --extra nlp` installs NLTK+spaCy. Also run:
  `uv run python -m nltk.downloader stopwords` and `uv run python -m spacy download en_core_web_sm`
- **Never call `embed_text()` directly in async context** — it blocks the event loop.
  It's always wrapped in `run_in_threadpool` inside `services.py`. Keep it that way.
- **Tests need Docker running** — testcontainers spins up a real pgvector container.
- **Rate limits in tests**: SlowAPI limits share in-memory state per IP key
  (`"testclient"` for all test requests). 60/min is safe for the current suite but
  watch if tests grow significantly.
- **Pyright dict invariance**: `dict[str, int]` is NOT a subtype of `dict[str, int | float]`.
  Use `cast(dict[str, int | float], {...})` to widen literal-inferred dict types.
- **Pydantic `model_construct()`**: Use in tests to bypass validation for `AppBrief`/`AppCatalog`
  fixtures that don't satisfy min-length or field-count constraints.
- **`/v1/claim` returns 200**, not 201 — FastAPI default for `@router.post`. Test assertions
  should use `status_code == 200`.
- **asyncpg UUID cast**: use `CAST(:param as uuid)` NOT `::uuid` inline cast with named parameters.
- **Module-level variable patching**: `monkeypatch.setattr(module, "engine", engine)` patches
  the local binding in the script's namespace — not `monkeypatch.setattr("dejaship.db.engine", ...)`.
- **rulesync**: `GEMINI.md`, `AGENTS.md`, `.agent/rules/claude.md`, etc. are generated.
  Edit `.rulesync/rules/CLAUDE.md`, then run `rulesync generate`.

## Environment Variables

All prefixed with `DEJASHIP_`. See `.env.example` for full list.
Key: `DATABASE_URL`, `EMBEDDING_MODEL`, `SIMILARITY_THRESHOLD`.

Experiment flags (all default `False`):
- `EMBEDDING_INCLUDE_CORE_MECHANIC` — toggle core_mechanic in embedding text
- `ENABLE_JACCARD_FILTER` + `JACCARD_THRESHOLD` + `JACCARD_MIN_KEYWORDS` — keyword overlap post-filter
- `ENABLE_KEYWORD_CLEANUP` + `KEYWORD_STOPWORDS` — strip generic SaaS terms before embedding
- `ENABLE_NLTK_STOPWORDS` — merge NLTK 179-word list (needs `ENABLE_KEYWORD_CLEANUP` + nlp extras)
- `ENABLE_SPACY_LEMMATIZATION` — lemmatize before Jaccard, "renewals"="renewal" (needs nlp extras)
- `ENABLE_TWO_STAGE_RETRIEVAL` — stage1 broad vector, stage2 mechanic-only rerank
- `ENABLE_RERANKER` + `RERANKER_MODEL` — ColBERT MaxSim reranker
- `ENABLE_HYBRID_SEARCH` — vector + PostgreSQL FTS with RRF fusion

## Search Quality

Baseline (2026-03-02, coverage-max corpus): FPR=0.72, recall=0.73, exact_top1=1.0
Root cause: generic SaaS vocabulary ("renewals", "subscription") inflates cross-domain similarity.
All 8 improvement flags are implemented but ALL DISABLED by default (empirically validated).
Feature ablation (2026-03-02): Jaccard filter harmful, mechanic rerank mediocre — no post-filter
improves FPR without disproportionate recall loss. Full-stack FPR=0.48 (much better than
cross-model benchmark 0.72). See `docs/decisions/2026-03-02-production-config.md`.
Model comparison result: BGE (default) outperforms snowflake and nomic on coverage-max.

Key docs:
- `docs/search-quality/false-positive-root-cause.md` — why FPR is 72%
- `docs/search-quality/improvement-approaches.md` — 11 ranked solutions with config flags
- `docs/search-quality/model-comparison.md` — fastembed 768-dim model analysis
- `docs/search-quality/feature-ablation.md` — Jaccard + mechanic rerank ablation results
- `docs/decisions/2026-03-02-embedding-text-strategy.md` — keywords-only experiment & revert
- `docs/decisions/2026-03-02-production-config.md` — validated production config (all defaults)
- `docs/agent-sim-coverage-max-status.md` — measured quality metrics & next steps
- `docs/plans/2026-03-02-search-quality-improvement-plan.md` — implementation plan
- `docs/plans/2026-03-02-feature-ablation-evaluation.md` — ablation harness plan (5 tasks)

Evaluation commands (no Docker needed — runs in-memory against pre-computed fixtures):
```bash
cd backend
uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval --model-set coverage-max
uv run python -m tests.agent_sim.tools.evaluate_similarity_thresholds --model-set coverage-max
uv run python -m tests.agent_sim.tools.evaluate_feature_ablation --model-set coverage-max
uv run python -m tests.agent_sim.tools.run_quality_suite --scenario smoke --model-set coverage-max
```

Full-stack integration test (requires Docker — uses testcontainers pgvector):
```bash
cd backend
uv run pytest tests/agent_sim/test_coverage_max_fullstack.py -v -m slow
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
