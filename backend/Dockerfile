# Stage 1: Download embedding model at build time
FROM python:3.12-slim AS model-downloader

RUN pip install --no-cache-dir fastembed

ARG EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='${EMBEDDING_MODEL}')"

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy baked model from build stage
COPY --from=model-downloader /root/.cache/fastembed /root/.cache/fastembed

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "dejaship.main:app", "--host", "0.0.0.0", "--port", "8000"]
