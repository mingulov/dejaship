# False Positive Root Cause Analysis

Date: 2026-03-02

## Problem

At `SIMILARITY_THRESHOLD=0.60` on the `coverage-max` corpus (17 models x 20 briefs):
- `false_positive_rate`: **0.7224** — 72% of retrieved results are from wrong overlap groups
- `recall_at_k`: 0.7348 — acceptable
- `exact_top1_rate`: 1.0 — perfect same-project retrieval

## Root Cause: Generic SaaS Vocabulary Contamination

The false positive problem is caused by a concentrated set of 7-8 globally generic keywords that appear across 70-80% of briefs regardless of domain.

### Worst Offender Keywords

| Keyword | Briefs | Groups | Total Occurrences |
|---------|--------|--------|-------------------|
| `renewals` | 8 | 7 | 85 |
| `subscription` | 16 | ~12 | high |
| `recurring-revenue` | 13 | ~10 | high |
| `revenue` | 13 | ~10 | high |
| `saas` | 12 | ~9 | high |
| `scheduling` | ~6 | ~5 | moderate |
| `retention` | ~8 | ~6 | moderate |

### Why This Happens

All 20 briefs in the corpus describe SaaS subscription products. They share business-model vocabulary even when their domains are completely different:
- HVAC service plans and ghost kitchen demand forecasting both use "subscription", "recurring-revenue", "renewals"
- The embedding model correctly identifies these texts as semantically similar — because at the vocabulary level, they **are** similar

### Additional Contamination: Stopwords as Keywords

The `phi` model family generates garbage keywords like "and", "with", "the", "for". The word `and` appears as a keyword in 14 of 20 briefs. These inflate cosine similarity between every pair.

### Worst Polluter Group

`field-service-recurring` (hvac + pest-control) is the worst polluter — it contaminates 8 other groups because its keywords are almost entirely generic service/subscription terms.

## Why Model Changes Won't Fix This

The embedding model is not the problem. It correctly captures that "HVAC subscription renewal tracking" and "ghost kitchen subscription demand forecasting" share vocabulary. The best alternative models (snowflake-arctic-embed-m, nomic-embed-text-v1.5) show at most 3.5% relative improvement on retrieval benchmarks — far less than the 72% FPR gap requires.

## Why Threshold Changes Won't Fix This

| Threshold | FPR | Recall | Trade-off |
|-----------|-----|--------|-----------|
| 0.55 | ~0.80 | ~0.82 | Too noisy |
| 0.60 | 0.72 | 0.73 | Current best balance |
| 0.65 | ~0.55 | ~0.51 | Recall drops too much |
| 0.75+ | low | collapsed | Unusable |

A single threshold cannot simultaneously serve broad matching (finding the same project claimed by different models) and narrow matching (excluding unrelated projects).

## Implication

The fix must come from **post-retrieval filtering or reranking** — not from changing the embedding model, the text construction, or the threshold alone. The most promising approaches are documented in [improvement-approaches.md](improvement-approaches.md).
