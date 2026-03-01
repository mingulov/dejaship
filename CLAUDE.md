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
- pgvector for vector similarity search

## Environment Variables

All prefixed with `DEJASHIP_`. See `.env.example` for full list.
Key: `DATABASE_URL`, `EMBEDDING_MODEL`, `SIMILARITY_THRESHOLD`.

## Conventions

- Python: async everywhere, SQLAlchemy 2.0 style, Pydantic for validation
- Tests: integration tests with real pgvector via testcontainers
- Commits: conventional commits (feat/fix/docs/refactor)
