# Production Configuration Decision

**Date:** 2026-03-02
**Decision:** Keep all defaults — post-retrieval features remain disabled

## Recommended Production Config

```env
# These are the validated defaults — no overrides needed
DEJASHIP_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
DEJASHIP_SIMILARITY_THRESHOLD=0.60
DEJASHIP_MAX_CLOSEST_RESULTS=10
DEJASHIP_KEYWORD_REPEAT=2
DEJASHIP_EMBEDDING_INCLUDE_CORE_MECHANIC=true

# Post-retrieval features — all DISABLED (empirically harmful or unvalidated)
DEJASHIP_ENABLE_JACCARD_FILTER=false
DEJASHIP_ENABLE_KEYWORD_CLEANUP=false
DEJASHIP_ENABLE_NLTK_STOPWORDS=false
DEJASHIP_ENABLE_SPACY_LEMMATIZATION=false
DEJASHIP_ENABLE_TWO_STAGE_RETRIEVAL=false
DEJASHIP_ENABLE_RERANKER=false
DEJASHIP_ENABLE_HYBRID_SEARCH=false
```

## Evidence

### What was tested

| Feature | Tested? | Verdict |
|---------|---------|---------|
| BGE bge-base-en-v1.5 | Yes (3 models compared) | **Best** — highest balanced score |
| Threshold 0.60 | Yes (sweep 0.50-0.90) | **Optimal** — balanced_score=2.3591 |
| KEYWORD_REPEAT=2 | Yes (ablation) | **Best** — current_combined variant wins |
| Core mechanic in embedding | Yes | **Keep** — removing loses 23% recall |
| Jaccard filter | Yes (6 thresholds) | **Harmful** — kills recall 2x faster than it reduces FPR |
| Mechanic-vector rerank | Yes (7 thresholds) | **Mediocre** — 1.4-13.7x recall loss per FPR reduction |
| Two-stage retrieval | No (prod path untested) | Unvalidated |
| ColBERT reranker | No | Unvalidated |
| Hybrid FTS | No | Unvalidated |
| Stopword cleanup | No | Unvalidated |

### Feature ablation data (coverage-max, threshold=0.60)

| Filter | Recall@k | FPR | Δ Recall | Δ FPR |
|--------|----------|-----|----------|-------|
| baseline | 0.7348 | 0.7224 | — | — |
| jaccard_05 | 0.2151 | 0.4436 | -0.520 | -0.279 |
| mechanic_55 | 0.6554 | 0.7028 | -0.079 | -0.020 |
| mechanic_60 | 0.4959 | 0.6406 | -0.239 | -0.082 |
| mechanic_65 | 0.2621 | 0.4909 | -0.473 | -0.232 |
| mechanic_70 | 0.0822 | 0.2479 | -0.653 | -0.475 |

### Full-stack test (real pgvector, 1 fixture per brief)

- Recall@k: **0.697**
- FPR: **0.476**
- Much better than cross-model in-memory eval (0.722 FPR) because real usage is single-query

## Why not enable anything

1. **Jaccard filter**: Empirically proven harmful. At threshold=0.05 (lowest tested), loses 52% recall for only 28% FPR reduction.

2. **Mechanic-vector rerank**: Every threshold loses recall faster than it reduces FPR. The in-memory mechanic_65 (closest to the two-stage STAGE2_THRESHOLD=0.65) drops 47% recall for only 23% FPR reduction.

3. **Two-stage retrieval**: The production implementation (broad stage1 → narrow stage2) might outperform the in-memory simulation. But without empirical validation through the full-stack test, enabling it risks degrading quality.

4. **ColBERT reranker, Hybrid FTS**: Not yet measured in the ablation framework.

## The structural problem

The high FPR in the coverage-max corpus is structural: 20 SaaS briefs sharing vocabulary ("subscription", "saas", "recurring-revenue"). In real-world usage with diverse intents (HVAC vs fintech vs healthcare), FPR would naturally be lower.

The full-stack test (FPR=0.476) already shows this: with 1 fixture per brief instead of 17 models × 20 briefs cross-product, FPR drops by 34%.

## Decision rules

- Do not enable features without coverage-max ablation data
- Any change must improve balanced_score (exact_top1 + overlap_hit + precision + recall - FPR)
- Recall loss must not exceed 10% for any FPR improvement
- Validate against coverage-max, not smoke/default alone
