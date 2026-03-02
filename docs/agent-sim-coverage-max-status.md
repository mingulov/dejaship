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

## Next Product Work

The next work should target DejaShip search quality, not more test scaffolding.

Priority order:

1. Improve embedding text construction in `backend/src/dejaship/embeddings.py`.
2. Add more discriminative weighting between `core_mechanic` and keywords instead of relying mainly on keyword repetition.
3. Consider a two-stage retrieval strategy:
   - broader first-pass candidate retrieval
   - stricter reranking for top results
4. Keep tuning against `coverage-max`, not `smoke` alone.

## Bottom Line

- publish for limited beta: yes
- publish as a broadly reliable polished search product: not yet

The main blocker is no longer missing tests. The blocker is measured search quality under diverse client phrasing.
