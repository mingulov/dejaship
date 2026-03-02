# Agent Sim Coverage-Max Status

Date: 2026-03-02

This report captures the current measured state of DejaShip search quality using the `agent_sim` harness and the `coverage-max` model corpus.

## Scope

- Baseline comparison corpus: `smoke`
- Realistic robustness corpus: `coverage-max`
- Evaluation artifacts:
  - `/tmp/agent-sim-quality-bundle-smoke-v2`
  - `/tmp/agent-sim-quality-bundle-coverage-max`
  - `/tmp/agent-sim-bundle-diff-smoke-vs-coverage-max.md`

## Main Result

`coverage-max` is the correct corpus for evaluating real customer robustness, because it reflects heterogeneous client phrasing across many fully covered models.

Compared to `smoke`, `coverage-max` shows:

- `cross_overlap_hit_rate`: `-0.0110`
- `cross_precision_at_k`: `-0.0882`
- `cross_recall_at_k`: `-0.0455`
- `cross_false_positive_rate`: `+0.1726`

Interpretation:

- exact same-project retrieval remains strong
- cross-model related-project retrieval becomes noisier
- DejaShip still works, but retrieval quality degrades materially once many different client/model phrasings are introduced

This is a real product signal, not a flaw in the test approach.

## Measured Best Settings So Far

From the `coverage-max` threshold and ablation reports:

- recommended `SIMILARITY_THRESHOLD`: `0.60`
- best tested embedding variant: `current_combined`
- best tested keyword repeat: `2`

Threshold observations:

- `0.60` is the best balanced point currently tested
- `0.65` reduces noise, but drops overlap recall too much
- `0.75` and above collapse useful overlap retrieval

At `0.60` on `coverage-max`:

- `exact_top1_rate`: `1.0`
- `overlap_hit_rate`: `0.9890`
- `overlap_precision_at_k`: `0.3577`
- `recall_at_k`: `0.7348`
- `false_positive_rate`: `0.7224`

Interpretation:

- retrieval finds relevant neighbors well
- but too many irrelevant neighbors are still returned
- the main current search problem is false positives under heterogeneous inputs

## Product Readiness Assessment

DejaShip is usable now:

- backend and MCP are working
- `agent_sim` is implemented and useful
- `backend/tests/agent_sim` passes
- the quality harness is strong enough to guide product tuning

Recommended release posture:

- suitable for beta or early customer trials
- not yet ideal for broad release if search quality is a central promise

Why:

- multi-model robustness is still not strong enough
- false-positive retrieval is too high on the realistic `coverage-max` corpus
- swarm reports still show weak crowded-skip discipline and same-group collision pressure

## Current Recommendation For Test Usage

Use model sets this way:

- `default`: fast stable regression and CI baseline
- `search-probe`: medium-cost heterogeneous analysis
- `coverage-max`: primary search-quality and robustness tuning corpus

The mistake would be optimizing only for `smoke` or `default` and assuming that broad client behavior is already handled.

## Embedding Strategy Experiment (2026-03-02)

A `keywords_only` embedding strategy was tested after a controlled 6-brief experiment suggested it would reduce FPR.

The lab experiment (1 model, 6 briefs) showed promising results:

- keywords-only at threshold 0.65: FPR=0.07 (vs 0.21 for current approach at same threshold)

However, the real `coverage-max` corpus (17 models × 20 briefs) showed a different outcome:

| Metric | current_combined @ 0.60 | keywords_only @ 0.65 | Delta |
|--------|------------------------|----------------------|-------|
| `exact_top1_rate` | 1.0000 | 0.9971 | -0.003 |
| `overlap_hit_rate` | 0.9890 | 0.8695 | **-0.120** |
| `recall_at_k` | 0.7348 | 0.5092 | **-0.226** |
| `false_positive_rate` | 0.7224 | 0.6144 | -0.108 |
| **balanced score** | **2.3591** | **2.1434** | **-0.216** |

Keywords-only at threshold 0.60 was even worse on FPR (0.7797 vs 0.7224 baseline).

**Conclusion**: `keywords_only` was reverted. The current `current_combined` strategy at threshold `0.60` remains best measured.

Why the lab was misleading: in the real corpus, 17 models generate different keywords for the same brief. The `core_mechanic` text is more canonical and consistent across models, so it provides discrimination that keyword bags cannot replicate under heterogeneous client phrasing.

See: `docs/decisions/2026-03-02-embedding-text-strategy.md` for full analysis.

## Next Product Work

The next work should target DejaShip search quality, not more test scaffolding.

Priority order:

1. **Two-stage retrieval** (highest expected impact — see decision doc):
   - Stage 1: broad candidate retrieval at threshold 0.55 using current combined embedding
   - Stage 2: rerank candidates by `core_mechanic`-only vector similarity at threshold 0.65
   - Requires schema migration to store a second `mechanic_embedding` vector per claim
2. Keep tuning against `coverage-max`, not `smoke` alone.
3. Avoid further single-metric optimization (FPR alone) without checking the balanced score.

## Bottom Line

- publish for limited beta: yes
- publish as a broadly reliable polished search product: not yet

The main blocker is no longer missing tests. The blocker is measured search quality under diverse client phrasing.
