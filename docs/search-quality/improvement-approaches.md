# Search Quality Improvement Approaches

Date: 2026-03-02

Ranked by expected impact on the false positive problem (FPR=0.7224 at threshold 0.60 on coverage-max).

## Tier 1: High Expected Impact

### 1. Two-Stage Retrieval with Mechanic Embedding

**Measured impact (in-memory ablation)**: mechanic_65 drops 47% recall for 23% FPR reduction (ratio 2:1). **Not recommended** without full-stack validation.
**Status**: Implemented (`ENABLE_TWO_STAGE_RETRIEVAL`), DISABLED by default.
**Complexity**: Medium (schema migration + new column + rerank logic)
**Latency impact**: +1 embedding computation per query

Decouple the two conflicting goals of a single embedding:
- Stage 1: Broad retrieval at threshold 0.55 using current combined embedding (prioritizes recall)
- Stage 2: Rerank candidates by `core_mechanic`-only vector similarity at threshold 0.65

In-memory ablation results (coverage-max, threshold=0.60):

| Filter | Recall@k | FPR | Δ Recall | Δ FPR | Ratio |
|--------|----------|-----|----------|-------|-------|
| mechanic_50 | 0.714 | 0.721 | -0.021 | -0.002 | 13.7:1 |
| mechanic_55 | 0.655 | 0.703 | -0.079 | -0.020 | 4.1:1 |
| mechanic_60 | 0.496 | 0.641 | -0.239 | -0.082 | 2.9:1 |
| mechanic_65 | 0.262 | 0.491 | -0.473 | -0.232 | 2.0:1 |
| mechanic_70 | 0.082 | 0.248 | -0.653 | -0.475 | 1.4:1 |

Every threshold loses recall faster than it reduces FPR. The production implementation (broad stage1 → narrow stage2) might outperform in-memory simulation, but lacks empirical validation.

Config flags: `ENABLE_TWO_STAGE_RETRIEVAL`, `STAGE1_THRESHOLD=0.55`, `STAGE2_THRESHOLD=0.65`, `STAGE2_CANDIDATE_MULTIPLIER=3`

See: `docs/decisions/2026-03-02-embedding-text-strategy.md`, `docs/decisions/2026-03-02-production-config.md`

### 2. Keyword Jaccard Post-Filter

**Measured impact**: At threshold=0.05 (lowest tested), loses 52% recall for 28% FPR reduction (ratio 1.86:1). **Empirically harmful.**
**Status**: Implemented (`ENABLE_JACCARD_FILTER`), DISABLED by default.
**Complexity**: Low (pure Python, no dependencies)
**Latency impact**: Negligible

In-memory ablation results (coverage-max, threshold=0.60):

| Filter | Recall@k | FPR | Δ Recall | Δ FPR |
|--------|----------|-----|----------|-------|
| jaccard_05 | 0.215 | 0.444 | -0.520 | -0.279 |
| jaccard_10 | 0.031 | 0.068 | -0.704 | -0.655 |
| jaccard_15 | 0.007 | 0.008 | -0.728 | -0.714 |

Jaccard is too aggressive: even at the lowest threshold, recall loss is nearly 2x the FPR reduction. The 20-brief SaaS corpus shares too much keyword vocabulary for Jaccard to discriminate effectively.

Config flags: `ENABLE_JACCARD_FILTER`, `JACCARD_THRESHOLD=0.15`, `JACCARD_MIN_KEYWORDS=3`

### 3. ColBERT Reranker

**Measured impact**: Not yet measured in ablation framework.
**Status**: Implemented (`ENABLE_RERANKER`), DISABLED by default.
**Complexity**: Medium (new model load, extra inference)
**Latency impact**: +50-200ms per query (depends on candidate count)

Uses fastembed `LateInteractionTextEmbedding` (NOT `TextCrossEncoder` which doesn't exist). Available models: `colbert-ir/colbertv2.0`, `answerdotai/answerai-colbert-small-v1`.

Config flags: `ENABLE_RERANKER`, `RERANKER_MODEL`

## Tier 2: Moderate Expected Impact

### 4. Hybrid Vector + Full-Text Search

**Measured impact**: Not yet measured in ablation framework.
**Status**: Implemented (`ENABLE_HYBRID_SEARCH`), DISABLED by default.
**Complexity**: Medium (tsvector column, GIN index, RRF fusion)
**Latency impact**: Negligible (parallel query)

Add a PostgreSQL `tsvector` column and GIN index for full-text search. Combine vector similarity with BM25-style text matching using Reciprocal Rank Fusion (RRF).

Config flags: `ENABLE_HYBRID_SEARCH`, `HYBRID_RRF_K=60`, `HYBRID_FTS_WEIGHT=0.3`

### 5. Category Pre-Filter

**Expected FPR reduction**: 15-30% (when category available)
**Status**: Not implemented.
**Complexity**: Low (optional field in claim/check API)
**Latency impact**: Negligible (WHERE clause filter)

Add an optional `category` field to claims. When present, filter vector search results to same category before returning.

### 6. Stopword/Generic Keyword Filtering

**Measured impact**: Not yet measured in ablation framework.
**Status**: Implemented (`ENABLE_KEYWORD_CLEANUP`, `ENABLE_NLTK_STOPWORDS`), DISABLED by default.
**Complexity**: Low (keyword cleanup function)
**Latency impact**: None

Config flags: `ENABLE_KEYWORD_CLEANUP`, `KEYWORD_STOPWORDS`, `ENABLE_NLTK_STOPWORDS`

### 7. Alternative Embedding Model

**Measured impact**: BGE outperforms alternatives on balanced_score.
**Status**: Validated — BGE (default) is best.
**Complexity**: Low (config change)

Tested: `snowflake/snowflake-arctic-embed-m`, `nomic-ai/nomic-embed-text-v1.5` vs `BAAI/bge-base-en-v1.5`. BGE wins on balanced score across coverage-max corpus.

See: `docs/search-quality/model-comparison.md` for detailed analysis.

## Tier 3: Low Expected Impact / High Complexity

### 8. Sparse SPLADE/BM25 Hybrid
High complexity (requires SPLADE model), moderate expected improvement. Deprioritized in favor of simpler hybrid FTS approach (#4).

### 9. PCA Dimension Reduction
Low expected impact. Reducing from 768 to 256 dims rarely improves discrimination for same-model comparisons.

### 10. Vector Whitening/Isotropy Correction
Low expected impact for our use case. Primarily helps when embedding space has strong anisotropy, which BGE doesn't exhibit strongly.

### 11. MIPS vs Cosine Distance
No impact — BGE produces unit-norm vectors, so cosine similarity equals inner product.

## Measured Status Summary (2026-03-02)

| Approach | Implemented | Measured | Verdict |
|----------|-------------|----------|---------|
| Keyword Jaccard | Yes | Yes | **Harmful** — 1.86:1 recall/FPR ratio |
| Mechanic rerank (two-stage proxy) | Yes | Yes | **Mediocre** — 1.4-13.7:1 ratio |
| ColBERT reranker | Yes | No | Unvalidated |
| Hybrid FTS | Yes | No | Unvalidated |
| Stopword cleanup | Yes | No | Unvalidated |
| NLTK stopwords | Yes | No | Unvalidated |
| spaCy lemmatization | Yes | No | Unvalidated |
| Embedding model | Yes | Yes | **BGE wins** |
| Category pre-filter | No | No | Not implemented |

**Decision**: All post-retrieval features remain DISABLED. See `docs/decisions/2026-03-02-production-config.md`.

**Decision rules for enabling any feature**:
- Must have coverage-max ablation data
- Must improve balanced_score (exact_top1 + overlap_hit + precision + recall - FPR)
- Recall loss must not exceed 10% for any FPR improvement

All approaches are behind config flags for A/B testing and easy rollback.
