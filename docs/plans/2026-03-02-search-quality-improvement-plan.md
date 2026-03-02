# Search Quality Improvement Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce false positive rate from 0.72 to <0.45 on coverage-max corpus while maintaining recall >0.65

**Architecture:** Incremental improvements behind config flags, validated against coverage-max after each change

**Tech Stack:** Python, FastAPI, SQLAlchemy, pgvector, fastembed, Alembic

**Evaluation command:**
```bash
cd backend
uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval --model-set coverage-max
```

**Baseline (2026-03-02):**
- `exact_top1_rate`: 1.0
- `overlap_hit_rate`: 0.989
- `recall_at_k`: 0.7348
- `false_positive_rate`: 0.7224
- `balanced_score`: 2.3591

---

## Task 1: Keyword Jaccard Post-Filter

**Priority:** Highest (lowest effort, immediate testable improvement)

**Files:**
- Modify: `backend/src/dejaship/config.py`
- Modify: `backend/src/dejaship/services.py`
- Create: `backend/tests/test_jaccard_filter.py`

### Step 1: Add config flags

Add to `config.py` Settings class:

```python
# Keyword Jaccard post-filter
# Filters vector search results by keyword set overlap.
# See docs/search-quality/improvement-approaches.md
ENABLE_JACCARD_FILTER: bool = False
JACCARD_THRESHOLD: float = 0.15
JACCARD_MIN_KEYWORDS: int = 3
```

### Step 2: Implement Jaccard filter function

Add to `services.py` (or a new `filters.py` if services.py is getting large):

```python
def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two keyword sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def apply_jaccard_filter(
    query_keywords: list[str],
    candidates: list[IntentRecord],
    threshold: float,
    min_keywords: int,
) -> list[IntentRecord]:
    """Filter candidates by keyword Jaccard similarity.

    If query has fewer than min_keywords, skip filtering (not enough signal).
    """
    if len(query_keywords) < min_keywords:
        return candidates
    query_set = set(kw.lower() for kw in query_keywords)
    result = []
    for candidate in candidates:
        candidate_set = set(kw.lower() for kw in candidate.keywords)
        if jaccard_similarity(query_set, candidate_set) >= threshold:
            result.append(candidate)
    return result
```

### Step 3: Wire into check_airspace

In `check_airspace` (services.py), after vector search results are returned:

```python
if settings.ENABLE_JACCARD_FILTER:
    results = apply_jaccard_filter(
        query_keywords=keywords,
        candidates=results,
        threshold=settings.JACCARD_THRESHOLD,
        min_keywords=settings.JACCARD_MIN_KEYWORDS,
    )
```

### Step 4: Write tests

```python
def test_jaccard_similarity_identical():
    assert jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"}) == 1.0

def test_jaccard_similarity_disjoint():
    assert jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

def test_jaccard_similarity_partial():
    result = jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
    assert abs(result - 0.5) < 0.01

def test_jaccard_similarity_empty():
    assert jaccard_similarity(set(), {"a"}) == 0.0

def test_apply_jaccard_filter_skips_few_keywords():
    """Filter is skipped when query has fewer than min_keywords."""
    # Should return all candidates unchanged
    ...

def test_apply_jaccard_filter_removes_unrelated():
    """Candidates with zero keyword overlap are filtered out."""
    ...
```

### Step 5: Run tests, then evaluate

```bash
uv run pytest tests/test_jaccard_filter.py -v
# Enable and evaluate:
DEJASHIP_ENABLE_JACCARD_FILTER=true uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval --model-set coverage-max
```

### Step 6: Commit

```bash
git add -A && git commit -m "feat: add keyword Jaccard post-filter behind config flag"
```

---

## Task 2: Stopword/Generic Keyword Cleanup

**Priority:** High (quick win, reduces vocabulary noise fed to embeddings)

**Files:**
- Modify: `backend/src/dejaship/config.py`
- Modify: `backend/src/dejaship/embeddings.py`
- Modify: `backend/tests/test_embeddings.py`

### Step 1: Add config flags

```python
# Keyword cleanup before embedding
# Removes generic SaaS terms that inflate cross-domain similarity.
# See docs/search-quality/false-positive-root-cause.md
ENABLE_KEYWORD_CLEANUP: bool = False
KEYWORD_STOPWORDS: str = "and,with,the,for,subscription,saas,recurring-revenue,revenue,renewals,retention"
```

### Step 2: Implement keyword cleanup

In `embeddings.py`:

```python
def clean_keywords(keywords: list[str], stopwords: set[str]) -> list[str]:
    """Remove stopwords and single-character keywords."""
    return [kw for kw in keywords if kw.lower() not in stopwords and len(kw) > 1]
```

Update `build_embedding_text` to apply cleanup when enabled:

```python
def build_embedding_text(core_mechanic: str, keywords: list[str]) -> str:
    if settings.ENABLE_KEYWORD_CLEANUP:
        stopwords = set(s.strip().lower() for s in settings.KEYWORD_STOPWORDS.split(",") if s.strip())
        keywords = clean_keywords(keywords, stopwords)
    # ... rest of existing logic
```

### Step 3: Write tests and evaluate

Test `clean_keywords` function directly. Then evaluate:

```bash
DEJASHIP_ENABLE_KEYWORD_CLEANUP=true uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval --model-set coverage-max
```

### Step 4: Commit

```bash
git commit -m "feat: add keyword stopword cleanup behind config flag"
```

---

## Task 3: Two-Stage Retrieval with Mechanic Embedding

**Priority:** Highest expected impact, but requires schema migration

**Files:**
- Modify: `backend/src/dejaship/config.py`
- Create: `backend/alembic/versions/xxx_add_mechanic_embedding.py` (migration)
- Modify: `backend/src/dejaship/models.py`
- Modify: `backend/src/dejaship/services.py`
- Modify: `backend/src/dejaship/embeddings.py`
- Modify: `backend/tests/test_services.py`

### Step 1: Add config flags

```python
# Two-stage retrieval
# Stage 1: broad candidate retrieval with combined embedding
# Stage 2: rerank by core_mechanic-only embedding similarity
# See docs/decisions/2026-03-02-embedding-text-strategy.md
ENABLE_TWO_STAGE_RETRIEVAL: bool = False
STAGE1_THRESHOLD: float = 0.55
STAGE2_THRESHOLD: float = 0.65
STAGE2_CANDIDATE_MULTIPLIER: int = 3
```

### Step 2: Schema migration

Add `mechanic_embedding` vector column to claims table:

```python
# alembic revision
mechanic_embedding = Column(Vector(768), nullable=True)
```

### Step 3: Update claim_intent

When storing a claim, also compute and store the mechanic-only embedding:

```python
mechanic_vector = await run_in_threadpool(embed_text, core_mechanic)
# Store alongside existing embedding
```

### Step 4: Implement two-stage check_airspace

```python
async def check_airspace_two_stage(
    core_mechanic: str,
    keywords: list[str],
    *,
    stage1_threshold: float,
    stage2_threshold: float,
    candidate_multiplier: int,
    top_k: int,
) -> list[IntentRecord]:
    # Stage 1: broad retrieval
    text = build_embedding_text(core_mechanic, keywords)
    vector = await run_in_threadpool(embed_text, text)
    candidates = await db_find_similar(vector, threshold=stage1_threshold, limit=top_k * candidate_multiplier)

    # Stage 2: rerank by mechanic similarity
    mechanic_vector = await run_in_threadpool(embed_text, core_mechanic)
    scored = []
    for claim in candidates:
        if claim.mechanic_embedding is not None:
            sim = cosine_similarity(mechanic_vector, claim.mechanic_embedding)
            if sim >= stage2_threshold:
                scored.append((sim, claim))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [claim for _, claim in scored[:top_k]]
```

### Step 5: Wire into services

In `check_airspace`, branch on config:

```python
if settings.ENABLE_TWO_STAGE_RETRIEVAL:
    return await check_airspace_two_stage(...)
else:
    # existing single-stage logic
```

### Step 6: Tests and evaluation

Integration tests with real pgvector. Then evaluate:

```bash
DEJASHIP_ENABLE_TWO_STAGE_RETRIEVAL=true uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval --model-set coverage-max
```

### Step 7: Commit

```bash
git commit -m "feat: add two-stage retrieval with mechanic embedding behind config flag"
```

---

## Task 4: Cross-Encoder Reranker

**Priority:** Powerful but adds latency and model dependency

**Files:**
- Modify: `backend/src/dejaship/config.py`
- Create: `backend/src/dejaship/reranker.py`
- Modify: `backend/src/dejaship/services.py`
- Modify: `backend/pyproject.toml` (if fastembed TextCrossEncoder needs extras)
- Create: `backend/tests/test_reranker.py`

### Step 1: Add config flags

```python
# Cross-encoder reranker
# Reranks vector search candidates using a cross-encoder model.
# Adds latency (+50-200ms) but improves precision.
# See docs/search-quality/improvement-approaches.md
ENABLE_CROSS_ENCODER: bool = False
CROSS_ENCODER_MODEL: str = "Xenova/ms-marco-MiniLM-L-6-v2"
CROSS_ENCODER_THRESHOLD: float = 0.5
```

### Step 2: Implement reranker module

```python
# reranker.py
from fastembed import TextCrossEncoder

_reranker: TextCrossEncoder | None = None

def load_reranker() -> TextCrossEncoder:
    global _reranker
    _reranker = TextCrossEncoder(model_name=settings.CROSS_ENCODER_MODEL)
    return _reranker

def rerank(query_text: str, candidates: list[IntentRecord], threshold: float) -> list[IntentRecord]:
    """Score each candidate against query using cross-encoder."""
    ...
```

### Step 3: Wire into services, test, evaluate

Same pattern as other features — behind `ENABLE_CROSS_ENCODER` flag.

### Step 4: Commit

```bash
git commit -m "feat: add cross-encoder reranker behind config flag"
```

---

## Task 5: Model Comparison Experiment

**Priority:** Low expected impact, but good to validate assumptions

**Files:**
- Modify: `backend/tests/agent_sim/_support/embedding_variants.py` (if needed)
- No production code changes needed — `DEJASHIP_EMBEDDING_MODEL` already exists

### Step 1: Run coverage-max with alternative models

```bash
# snowflake
DEJASHIP_EMBEDDING_MODEL="snowflake/snowflake-arctic-embed-m" \
  uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval --model-set coverage-max

# nomic
DEJASHIP_EMBEDDING_MODEL="nomic-ai/nomic-embed-text-v1.5" \
  uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval --model-set coverage-max
```

### Step 2: Compare results

Document in `docs/search-quality/model-comparison.md`.

### Step 3: Commit findings

```bash
git commit -m "docs: add model comparison experiment results"
```

---

## Task 6: Hybrid Vector + Full-Text Search

**Priority:** Medium — good complement but more infrastructure

**Files:**
- Create: migration adding `search_tsvector` column + GIN index
- Modify: `backend/src/dejaship/models.py`
- Modify: `backend/src/dejaship/services.py`
- Modify: `backend/src/dejaship/config.py`

### Step 1: Add config flags

```python
# Hybrid search (vector + full-text)
ENABLE_HYBRID_SEARCH: bool = False
HYBRID_RRF_K: int = 60
HYBRID_FTS_WEIGHT: float = 0.3
```

### Step 2: Schema migration

Add tsvector column with GIN index, populated from keywords + core_mechanic.

### Step 3: Implement RRF fusion

Combine vector rank and FTS rank using Reciprocal Rank Fusion:

```python
def rrf_score(vector_rank: int, fts_rank: int, k: int = 60) -> float:
    return (1 - fts_weight) / (k + vector_rank) + fts_weight / (k + fts_rank)
```

### Step 4: Tests and evaluation

### Step 5: Commit

---

## Evaluation Strategy

After implementing each task:

1. Run with the feature enabled:
   ```bash
   DEJASHIP_ENABLE_<FEATURE>=true uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval --model-set coverage-max
   ```

2. Compare against baseline:
   - `false_positive_rate` must decrease
   - `recall_at_k` must not drop more than 10%
   - `balanced_score` must improve

3. Record results in `docs/search-quality/experiment-results.md`

4. Try combinations of features that individually improve metrics

## Success Criteria

- FPR < 0.45 (from 0.72) on coverage-max
- recall_at_k > 0.65 (from 0.73)
- balanced_score > 2.60 (from 2.36)
- All existing tests still pass
- No latency regression >200ms per query
