# Agent Sim Quality Framework

## Purpose

`backend/tests/agent_sim/` is not only a test suite. It is the main evaluation harness for judging whether DejaShip behaves well under realistic MCP-driven agent usage.

It should help answer:

1. Does the MCP workflow remain correct under many concurrent agents?
2. Does similarity search surface the right competing or adjacent ideas?
3. Does the current embedding text strategy create good separation between unrelated projects and useful collision pressure between related ones?
4. Can DejaShip be tuned using measurable outcomes rather than intuition?

The suite is intentionally split into two layers:

- `backend/tests/agent_sim/`: local test assets, support code, generators, and replay tools
- `docs/`: durable project documentation for how the quality framework should be used to improve the product

## What The Suite Tests Today

Current implemented capabilities:

- structured 20-brief application catalog with designed overlap groups
- stored LLM fixture corpus for deterministic replay
- MCP swarm replay against the real backend `/mcp` surface
- per-agent event timelines
- per-model summaries
- stale-claim cleanup simulation
- report export for human and LLM review
- cross-model retrieval evaluation using the real embedding text builder

Current supported baseline:

- `smoke` is the offline supported baseline
- non-live scenarios are expected to use stored fixtures only
- broader model coverage is optional and can be expanded later

## Key Design Principle

The suite must evaluate DejaShip as a ledger/search system, not as a prompt demo.

That means the most important outcomes are:

- whether an already claimed project is discoverable by another agent
- whether related ideas create visible crowding
- whether unrelated ideas stay separate
- whether agents make better claim/skip/revise decisions because the MCP search results are useful

Model choice for intent generation is not something DejaShip controls, but it still matters in evaluation:

- different clients will produce different intent payloads
- DejaShip should remain robust across that diversity
- cross-model retrieval is therefore a system-quality metric, not a client-prescription metric

## Most Useful Metric Families

### 1. Retrieval Quality

These metrics directly measure whether search behaves well.

- `exact_cross_model_top1_rate`
  Meaning: if model A claims a brief and model B checks the same brief, does A's claim appear at rank 1.
- `exact_cross_model_hit_rate`
  Meaning: does the exact same brief appear anywhere in the retrieved set.
- `related_overlap_hit_rate`
  Meaning: when the catalog says a brief should collide with another group member, does search surface at least one of those related claims.
- `false_positive_rate`
  Meaning: for unrelated briefs, how often does search still return a claim.
- `precision_at_k`
  Meaning: among retrieved claims, how many are actually from expected or adjacent overlap groups.
- `recall_at_k`
  Meaning: among relevant claims that exist, how many were retrieved.
- `rank_of_first_relevant`
  Meaning: how early the first relevant result appears.
- `retrieval_asymmetry`
  Meaning: model A can find model B's claim, but model B cannot find model A's.

### 2. Decision Quality

These metrics measure whether the returned search results produce good agent behavior.

- `claim_when_clear_rate`
  Meaning: when there is no relevant crowding, agents claim rather than hesitate.
- `skip_when_crowded_rate`
  Meaning: overlap-averse agents skip or revise when the airspace is crowded.
- `revision_success_rate`
  Meaning: after a crowded initial check, revised or secondary ideas become claimable.
- `duplicate_claim_rate`
  Meaning: multiple agents still claim the same or near-identical opportunity.

### 3. Lifecycle Quality

These metrics show whether claimed ideas resolve cleanly.

- `ship_rate_by_model`
- `abandon_rate_by_model`
- `stale_cleanup_rate`
- `time_to_terminal_state`
- `open_claim_rate`

### 4. Search and Embedding Tuning

These metrics help tune the product itself.

- `threshold_sensitivity_curve`
  Compare retrieval outcomes across several similarity thresholds.
- `keyword_repeat_sensitivity`
  Measure effect of changing `KEYWORD_REPEAT`.
- `core_vs_keywords_ablation`
  Compare embedding text built from:
  - mechanic only
  - keywords only
  - current combined weighting
- `overlap_group_cohesion`
  Average within-group similarity.
- `overlap_group_separation`
  Average between-group similarity.
- `brief_separability_score`
  Whether unrelated briefs are incorrectly close.

### 5. Operational MCP Quality

- `tool_call_success_rate`
- `update_success_rate`
- `invalid_transition_rate`
- `rate_limit_trigger_rate`
- `latency_per_tool`
- `latency_per_scenario`

## Current Highest-Value Scores

If only a small set of metrics is maintained and reviewed regularly, these should be the first ones:

1. `exact_cross_model_top1_rate`
2. `related_overlap_hit_rate`
3. `false_positive_rate`
4. `precision_at_k`
5. `rank_of_first_relevant`
6. `threshold_sensitivity_curve`
7. `retrieval_asymmetry`
8. `ship_rate_by_model`

These are the metrics most likely to improve:

- similarity threshold tuning
- embedding text construction
- keyword weighting
- neighborhood usefulness for real MCP users

## How To Use Agent Sim To Improve DejaShip

Recommended loop:

1. Run swarm replay on the smoke baseline.
2. Export a report artifact.
3. Run cross-model retrieval analysis.
4. Review quality flags and retrieval metrics.
5. Change one search-related variable at a time.
6. Re-run and compare.

Good candidates for one-variable changes:

- `SIMILARITY_THRESHOLD`
- `KEYWORD_REPEAT`
- `build_embedding_text()`
- keyword-builder ranking rules
- maximum retrieved result count

The suite should be treated as a regression harness for semantic behavior:

- if a change improves one metric but damages false-positive rate badly, it is not an overall improvement
- if a change improves same-model retrieval but hurts cross-model retrieval, it may reduce robustness for real clients

Current measured recommendation from the default stored-fixture corpus:

- keep the current combined embedding text strategy
- keep `KEYWORD_REPEAT=2`
- lower `SIMILARITY_THRESHOLD` from `0.75` to `0.60`

Reason:

- `0.75` preserved exact-match retrieval but collapsed cross-model overlap retrieval almost completely
- `0.60` preserved exact retrieval while restoring useful related-overlap discovery
- current combined text with `KEYWORD_REPEAT=2` remained the best balanced default among the tested text variants

## Current Command Set

Run the offline suite:

```bash
cd backend
uv run pytest tests/agent_sim -q
```

Export a scenario report:

```bash
cd backend
uv run python -m tests.agent_sim.tools.run_agent_sim_report \
  --scenario smoke \
  --seed 13 \
  --output-json /tmp/agent-sim-report.json \
  --output-md /tmp/agent-sim-report.md
```

Summarize fixture coverage:

```bash
cd backend
uv run python -m tests.agent_sim.tools.summarize_llm_fixtures
```

Evaluate cross-model retrieval:

```bash
cd backend
uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval \
  --model-set default \
  --output-json /tmp/agent-sim-cross-model.json \
  --output-md /tmp/agent-sim-cross-model.md
```

Evaluate threshold sensitivity:

```bash
cd backend
uv run python -m tests.agent_sim.tools.evaluate_similarity_thresholds \
  --model-set default \
  --output-json /tmp/agent-sim-thresholds.json \
  --output-md /tmp/agent-sim-thresholds.md
```

Evaluate embedding-text ablation:

```bash
cd backend
uv run python -m tests.agent_sim.tools.evaluate_embedding_ablation \
  --model-set default \
  --output-json /tmp/agent-sim-ablation.json \
  --output-md /tmp/agent-sim-ablation.md
```

Run the full quality bundle:

```bash
cd backend
uv run python -m tests.agent_sim.tools.run_quality_suite \
  --scenario smoke \
  --model-set default \
  --output-dir /tmp/agent-sim-quality-bundle
```

## Implementation Plan For Full Metric Coverage

### Phase 1: Complete Retrieval Baseline

Goal: make retrieval quality measurable enough to guide search tuning.

Implement:

- `false_positive_rate`
- `rank_of_first_relevant`
- `recall_at_k`
- `retrieval_asymmetry` summary
- threshold sweep tool over current default fixture corpus

Expected outcome:

- DejaShip can compare thresholds and immediately see whether retrieval got better or noisier.

### Phase 2: Add Search Ablation Analysis

Goal: understand whether the current embedding text is actually the right one.

Implement:

- `core_vs_keywords_ablation`
- `keyword_repeat_sensitivity`
- within-group and between-group similarity summaries

Expected outcome:

- the project can decide whether keywords are over-weighted, under-weighted, or correctly balanced.

### Phase 3: Expand Decision Metrics

Goal: understand whether good retrieval actually changes agent behavior.

Implement:

- `claim_when_clear_rate`
- `skip_when_crowded_rate`
- `revision_success_rate`
- `duplicate_claim_rate` refined by overlap group
- per-persona behavior metrics

Expected outcome:

- reports explain whether MCP search is merely returning data or actually helping agents act correctly.

### Phase 4: Improve Lifecycle and Timeline Analysis

Goal: make long-run operational behavior analyzable.

Implement:

- step-based `time_to_terminal_state`
- unresolved-claim aging metrics
- stale-cleanup burden by model and persona
- report artifact history comparison

Expected outcome:

- DejaShip can judge whether a search change creates healthier final project outcomes.

### Phase 5: Stress and Reliability Analysis

Goal: ensure the MCP surface remains useful under scale.

Implement:

- `hundred-agent` reporting as a documented explicit stress run
- rate-limit and latency summaries
- concurrency-focused retrieval quality checks

Expected outcome:

- quality work does not accidentally regress under realistic concurrency.

## Decision Rules

Suggested interpretation rules:

- Raise concern if `exact_cross_model_top1_rate` drops materially after a search change.
- Raise concern if `false_positive_rate` rises while overlap-hit metrics stay flat.
- Prefer changes that improve both `related_overlap_hit_rate` and `precision_at_k`.
- Treat higher `duplicate_claim_rate` as a likely search-quality regression unless the scenario intentionally forces ambiguous collisions.
- Treat strong retrieval asymmetry as a robustness warning: DejaShip may work well only for certain client prompt styles.

## Recommended Reporting Artifacts

For each serious evaluation run, keep:

- JSON report from swarm replay
- Markdown summary from swarm replay
- JSON report from cross-model retrieval
- Markdown summary from cross-model retrieval
- JSON report from threshold sweep
- JSON report from embedding ablation
- run metadata:
  - commit SHA
  - threshold
  - keyword repeat
  - embedding model
- model set used

That gives both humans and LLMs enough context to explain whether DejaShip quality improved or regressed.

`run_quality_suite.py` is the intended command for generating this bundle in one step.
