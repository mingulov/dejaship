# Search Quality Improvement Approaches

Date: 2026-03-02

Ranked by expected impact on the false positive problem (FPR=0.7224 at threshold 0.60 on coverage-max).

## Tier 1: High Expected Impact

### 1. Two-Stage Retrieval with Mechanic Embedding (Priority #1)

**Expected FPR reduction**: 30-50%
**Complexity**: Medium (schema migration + new column + rerank logic)
**Latency impact**: +1 embedding computation per query

Decouple the two conflicting goals of a single embedding:
- Stage 1: Broad retrieval at threshold 0.55 using current combined embedding (prioritizes recall)
- Stage 2: Rerank candidates by `core_mechanic`-only vector similarity at threshold 0.65

Why it should work: `core_mechanic` text is domain-specific prose ("HVAC maintenance plan renewal tracking" vs "ghost kitchen demand forecasting"). When stripped of keyword noise, these descriptions are highly discriminative between domains.

Requires: `mechanic_embedding` column in claims table (schema migration), storing a second vector per claim.

Config flags needed:
- `ENABLE_TWO_STAGE_RETRIEVAL: bool = False`
- `STAGE1_THRESHOLD: float = 0.55`
- `STAGE2_THRESHOLD: float = 0.65`
- `STAGE2_CANDIDATE_MULTIPLIER: int = 3`

See: `docs/decisions/2026-03-02-embedding-text-strategy.md` for implementation sketch.

### 2. Keyword Jaccard Post-Filter

**Expected FPR reduction**: 10-20%
**Complexity**: Low (pure Python, no dependencies)
**Latency impact**: Negligible

After vector retrieval, compute Jaccard similarity between the query's keyword set and each candidate's stored keywords. Filter out candidates below a Jaccard threshold.

Why it should work: Unrelated domains use different specialist terms even when their generic SaaS vocabulary overlaps. "hvac", "technician", "dispatch" vs "ghost-kitchen", "prep-station", "demand-forecast" have zero keyword overlap.

Config flags needed:
- `ENABLE_JACCARD_FILTER: bool = False`
- `JACCARD_THRESHOLD: float = 0.15`
- `JACCARD_MIN_KEYWORDS: int = 3` (skip filter if too few keywords to be meaningful)

### 3. Cross-Encoder Reranker

**Expected FPR reduction**: 20-40%
**Complexity**: Medium (new model load, extra inference)
**Latency impact**: +50-200ms per query (depends on candidate count)

Use fastembed's built-in `TextCrossEncoder` (e.g., `Xenova/ms-marco-MiniLM-L-6-v2`) to rerank candidates. Cross-encoders process query-document pairs jointly and are more accurate than bi-encoders for reranking.

Why it should work: Cross-encoders capture fine-grained semantic relationships that bag-of-words embeddings miss. They can distinguish "HVAC subscription tracking" from "pet food subscription tracking" even when the bi-encoder embeddings are close.

Config flags needed:
- `ENABLE_CROSS_ENCODER: bool = False`
- `CROSS_ENCODER_MODEL: str = "Xenova/ms-marco-MiniLM-L-6-v2"`
- `CROSS_ENCODER_THRESHOLD: float = 0.5`

## Tier 2: Moderate Expected Impact

### 4. Hybrid Vector + Full-Text Search

**Expected FPR reduction**: 10-25%
**Complexity**: Medium (tsvector column, GIN index, RRF fusion)
**Latency impact**: Negligible (parallel query)

Add a PostgreSQL `tsvector` column and GIN index for full-text search. Combine vector similarity with BM25-style text matching using Reciprocal Rank Fusion (RRF).

Why it should help: BM25 rewards exact token matches, so "hvac" in query AND document gets a boost that generic-SaaS-vocabulary matches don't.

Config flags needed:
- `ENABLE_HYBRID_SEARCH: bool = False`
- `HYBRID_RRF_K: int = 60`
- `HYBRID_FTS_WEIGHT: float = 0.3`

### 5. Category Pre-Filter

**Expected FPR reduction**: 15-30% (when category available)
**Complexity**: Low (optional field in claim/check API)
**Latency impact**: Negligible (WHERE clause filter)

Add an optional `category` field to claims. When present, filter vector search results to same category before returning. Categories could be: field-service, food-ops, fintech, creator-tools, health, etc.

Config flags needed:
- `ENABLE_CATEGORY_FILTER: bool = False`

### 6. Stopword/Generic Keyword Filtering

**Expected FPR reduction**: 5-15%
**Complexity**: Low (keyword cleanup function)
**Latency impact**: None

Remove known-generic keywords before embedding: "subscription", "saas", "recurring-revenue", "revenue", "and", "with", "the", "for". This reduces the shared vocabulary that inflates cross-domain similarity.

Config flags needed:
- `ENABLE_KEYWORD_CLEANUP: bool = False`
- `KEYWORD_STOPWORDS: str = ""` (comma-separated list, or load from file)

### 7. Alternative Embedding Model

**Expected FPR reduction**: 2-5%
**Complexity**: Low (config change)
**Latency impact**: Varies by model

Test `snowflake/snowflake-arctic-embed-m` or `nomic-ai/nomic-embed-text-v1.5` as alternatives to `BAAI/bge-base-en-v1.5`.

Already configurable via `DEJASHIP_EMBEDDING_MODEL`.

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

## Recommended Implementation Order

1. **Keyword Jaccard post-filter** — lowest effort, immediate testable improvement
2. **Two-stage retrieval** — highest expected impact, but needs schema migration
3. **Stopword keyword cleanup** — quick win, reduces vocabulary noise
4. **Cross-encoder reranker** — powerful but adds latency and model dependency
5. **Hybrid FTS** — good complement to vector search but more infrastructure
6. **Model comparison experiment** — minor improvement, good to validate assumptions
7. **Category pre-filter** — useful if clients provide category data

All approaches should be behind config flags for A/B testing and easy rollback.
