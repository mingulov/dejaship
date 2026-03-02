# Embedding Text Strategy Decision

Date: 2026-03-02

## Decision

Keep the current `build_embedding_text` strategy: **first 10 keywords repeated twice, core_mechanic appended once** (`KEYWORD_REPEAT=2`), at **similarity threshold 0.60**.

The `keywords_only` hypothesis was tested and **did not improve** over the baseline on the realistic `coverage-max` corpus.

## Problem Statement

At threshold 0.60 on `coverage-max`:

- `false_positive_rate`: 0.7224 — too many unrelated projects retrieved
- `recall_at_k`: 0.7348 — related projects found at acceptable rate
- `overlap_hit_rate`: 0.989 — true neighbors found reliably
- `exact_top1_rate`: 1.0 — same-project exact retrieval is perfect

The question was: does changing the embedding text construction reduce false positives?

## What Was Tested

### Hypothesis

The hypothesis was that `core_mechanic` text inflates false-positive similarity because all SaaS product mechanics share generic vocabulary: "automated", "renewal", "tracking", "recurring revenue". Removing `core_mechanic` from the embedding and using keywords only should produce more domain-specific, discriminative vectors.

This was supported by a controlled single-model experiment on a 6-brief subset, which showed:

- Keywords-only at threshold 0.65: FPR=0.071 (vs 0.21 for current approach at same threshold)
- Keywords-only at threshold 0.65: TPR=1.00 (no true pairs lost in the subset)

### Real Corpus Result

When tested on the full `coverage-max` corpus (17 models × 20 briefs):

| Metric | Old (current_combined, threshold 0.60) | New (keywords_only, threshold 0.65) | Delta |
|--------|----------------------------------------|--------------------------------------|-------|
| `exact_top1_rate` | 1.0000 | 0.9971 | -0.003 |
| `overlap_hit_rate` | 0.9890 | 0.8695 | **-0.120** |
| `overlap_precision_at_k` | 0.3577 | 0.3820 | +0.024 |
| `recall_at_k` | 0.7348 | 0.5092 | **-0.226** |
| `false_positive_rate` | 0.7224 | 0.6144 | -0.108 |
| **balanced score** | **2.3591** | **2.1434** | **-0.216** |

Keywords-only at threshold 0.60 was even worse:

| Metric | Old at 0.60 | Keywords-only at 0.60 | Delta |
|--------|-------------|----------------------|-------|
| `false_positive_rate` | 0.7224 | **0.7797** | +0.057 (worse) |
| `recall_at_k` | 0.7348 | 0.7121 | -0.023 |

### Why the Lab Experiment Was Misleading

The controlled experiment used one model's keywords per brief. In the real corpus, 17 different models generate different keyword sets for the same brief, because each model interprets the prompt differently.

In that multi-model setting:

- Cross-model keyword similarity for **unrelated briefs** is higher than in single-model testing, because generic SaaS terms ("renewals", "retention", "subscription") appear across many model outputs regardless of domain.
- The `core_mechanic` text is more **canonical and consistent** across models — it describes the product in domain-specific prose that is harder to confuse across categories.
- Removing `core_mechanic` from the embedding actually **increases** cross-model FPR because the remaining keyword bags are noisier across models.

## Current Status

Both changes were reverted:

- `build_embedding_text`: kept at `kw*2 + core_mechanic` (original)
- `SIMILARITY_THRESHOLD`: kept at 0.60

The current approach remains the best measured configuration.

## Future: Two-Stage Retrieval

The two-stage retrieval approach is the most promising path forward for reducing FPR while maintaining recall. It was not implemented in this session.

### Why It Is Expected to Help

The FPR problem is fundamentally that a **single embedding vector** must simultaneously serve two very different goals:

1. Find the **same project** claimed by a different model (requires broad matching)
2. **Not return** unrelated projects (requires narrow matching)

These goals are in tension. A lower threshold catches more true neighbors but also more noise. A higher threshold cuts noise but loses true neighbors.

Two-stage retrieval decouples these goals:

- **Stage 1 (broad retrieval)**: Use the current embedding and a low threshold (e.g., 0.55) to build a candidate set. This prioritizes recall and ensures true neighbors are not missed.
- **Stage 2 (reranking)**: Score the candidate set using a secondary signal that is more discriminative than the first-pass embedding. Discard candidates below the secondary threshold.

### Candidate Reranking Signals

In priority order:

1. **Core mechanic text similarity** — embed only `core_mechanic` (stripped of keywords) and compute cosine similarity. Because different product domains have very different mechanics ("HVAC maintenance plan renewal" vs "ghost kitchen demand forecasting"), this signal adds discrimination without introducing keyword noise.

2. **Overlap group membership** — the catalog's `expected_overlap_group` field could be used to build a lightweight domain classifier. Claims from the same domain are more likely to be true neighbors.

3. **Keyword Jaccard similarity** — count of shared keywords divided by union. A quick exact-match overlap metric that rewards briefs using the same specialist terms.

4. **Metadata signals** — target customer category, pricing shape, or distribution channel as structured filters applied before or after the vector search.

### Implementation Sketch

```python
async def check_airspace_two_stage(
    core_mechanic: str,
    keywords: list[str],
    *,
    stage1_threshold: float = 0.55,
    stage2_threshold: float = 0.65,
    top_k: int = 10,
) -> list[IntentRecord]:
    # Stage 1: broad retrieval with current combined embedding
    text = build_embedding_text(core_mechanic, keywords)
    vector = await run_in_threadpool(embed_text, text)
    candidates = await db_find_similar(vector, threshold=stage1_threshold, limit=top_k * 3)

    # Stage 2: rerank by core_mechanic-only similarity
    mechanic_vector = await run_in_threadpool(embed_text, core_mechanic)
    scored = []
    for claim in candidates:
        mechanic_sim = cosine(mechanic_vector, claim.mechanic_vector)
        if mechanic_sim >= stage2_threshold:
            scored.append((mechanic_sim, claim))
    scored.sort(reverse=True)
    return [claim for _, claim in scored[:top_k]]
```

This requires storing a second vector (`mechanic_vector`) per claim in the database — a schema migration — but uses the same `embed_text` function and adds no new model dependency.

### Expected Impact

Based on the controlled 6-brief experiment:

- Core-mechanic-only at threshold 0.65 is highly discriminative between domains
- Combined with the first-stage pass ensuring true neighbors are not lost, this should reduce FPR significantly while maintaining recall

Testing this properly requires:

1. A schema migration to add `mechanic_embedding` column
2. Updating `claim_intent` to compute and store the mechanic embedding
3. Updating `check_airspace` to use the two-stage logic
4. Re-running `evaluate_cross_model_retrieval --model-set coverage-max` and comparing

## Decision Rules Going Forward

- Do not tune against `smoke` or `default` alone — use `coverage-max` as the primary evaluation corpus.
- Any change to `build_embedding_text`, `SIMILARITY_THRESHOLD`, or `KEYWORD_REPEAT` must be validated against `coverage-max` before merge.
- Treat improvements to FPR that come at more than 10% cost to `recall_at_k` or `overlap_hit_rate` as not acceptable.
- The balanced score (`exact_top1_rate + overlap_hit_rate + precision_at_k + recall_at_k - false_positive_rate`) is the primary evaluation metric for comparing embedding strategies.
