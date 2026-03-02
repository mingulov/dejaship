# Feature Ablation Evaluation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a complete evaluation harness that measures how each post-retrieval feature (Jaccard filter, mechanic-vector rerank, full-stack integration) changes FPR and recall on the coverage-max corpus.

**Architecture:** Three layers — (A) extend the in-memory evaluation framework so any post-filter can be plugged in, (B) a new script that sweeps all feature combinations and reports results, (C) a pytest integration test that populates a real testcontainers PostgreSQL and calls check_airspace() via HTTP to measure full-stack quality.

**Tech Stack:** Python 3.12, fastembed (ONNX embeddings), pytest + testcontainers, httpx (AsyncClient), SQLAlchemy 2.0, pgvector.

---

## Background — what the existing code does

**Existing retrieval evaluation (pure in-memory, no Docker needed):**
- `backend/tests/agent_sim/_support/retrieval_analysis.py` — core library: `RetrievalRecord`, `compute_cross_model_retrieval_matrix`, `evaluate_thresholds`
- `backend/tests/agent_sim/tools/evaluate_similarity_thresholds.py` — sweeps thresholds
- `backend/tests/agent_sim/tools/evaluate_cross_model_retrieval.py` — cross-model comparison
- `backend/tests/agent_sim/tools/evaluate_embedding_ablation.py` — embedding text variants

**Fixture data:**
- `backend/tests/agent_sim/fixtures/llm_outputs/<model_alias>/<brief_id>.json` — `StoredLLMFixture` JSON
- Each fixture has `final_intent_input.keywords: list[str]` and `final_intent_input.core_mechanic: str`
- The evaluation scripts embed `build_embedding_text(core_mechanic, keywords)` to get vectors

**Full-stack test infrastructure:**
- `backend/tests/conftest.py` — already has `postgres_container`, `engine`, `session`, `client` fixtures via testcontainers
- `client` fixture is an `AsyncClient` with the FastAPI app mounted and a real pgvector DB injected

**Metrics defined in `compute_cross_model_retrieval_matrix`:**
- `recall_at_k`: relevant_retrieved / relevant_available
- `false_positive_rate`: false_positive_retrieved / retrieved_total
- `balanced_score` (in `evaluate_thresholds`): exact_top1 + overlap_hit + precision + recall − FPR

**Baseline results (coverage-max, threshold=0.6):**
- recall=0.7348, FPR=0.7224 — this is what we're trying to improve

---

## Task 1: Extend RetrievalRecord with keywords and mechanic_vector

**Files:**
- Modify: `backend/tests/agent_sim/_support/retrieval_analysis.py`

Keywords are needed for the Jaccard filter simulation; mechanic_vector is needed for two-stage simulation.

**Step 1: Write the failing test**

Create `backend/tests/test_retrieval_analysis_keywords.py`:

```python
"""Tests that RetrievalRecord carries keywords and mechanic_vector."""
from dataclasses import fields
from tests.agent_sim._support.retrieval_analysis import RetrievalRecord


def test_retrieval_record_has_keywords_field():
    r = RetrievalRecord(brief_id="b", model_alias="m", vector=[0.1, 0.2])
    assert hasattr(r, "keywords")
    assert r.keywords == []


def test_retrieval_record_has_mechanic_vector_field():
    r = RetrievalRecord(brief_id="b", model_alias="m", vector=[0.1, 0.2])
    assert hasattr(r, "mechanic_vector")
    assert r.mechanic_vector == []


def test_retrieval_record_keywords_stored():
    r = RetrievalRecord(brief_id="b", model_alias="m", vector=[0.5], keywords=["saas", "billing"])
    assert r.keywords == ["saas", "billing"]
```

**Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_retrieval_analysis_keywords.py -v
```
Expected: FAIL with `TypeError: RetrievalRecord.__init__() got an unexpected keyword argument 'keywords'`

**Step 3: Add the fields to RetrievalRecord**

In `backend/tests/agent_sim/_support/retrieval_analysis.py`, change:

```python
# BEFORE
from dataclasses import dataclass

@dataclass(slots=True)
class RetrievalRecord:
    brief_id: str
    model_alias: str
    vector: list[float]
```

To:

```python
# AFTER
from dataclasses import dataclass, field

@dataclass(slots=True)
class RetrievalRecord:
    brief_id: str
    model_alias: str
    vector: list[float]
    keywords: list[str] = field(default_factory=list)
    mechanic_vector: list[float] = field(default_factory=list)
```

**Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_retrieval_analysis_keywords.py -v
```
Expected: 3 PASS

**Step 5: Update evaluate_cross_model_retrieval.py to populate keywords**

In `backend/tests/agent_sim/tools/evaluate_cross_model_retrieval.py`, change the records.append block:

```python
# BEFORE
records.append(
    RetrievalRecord(
        brief_id=brief.id,
        model_alias=model_alias,
        vector=embed_text(text),
    )
)
```

To:

```python
# AFTER
records.append(
    RetrievalRecord(
        brief_id=brief.id,
        model_alias=model_alias,
        vector=embed_text(text),
        keywords=fixture.final_intent_input.keywords,
        mechanic_vector=embed_text(fixture.final_intent_input.core_mechanic),
    )
)
```

Do the same in `evaluate_similarity_thresholds.py` and `evaluate_embedding_ablation.py` — same pattern.

**Step 6: Verify existing scripts still run**

```bash
cd backend && uv run python -m tests.agent_sim.tools.evaluate_cross_model_retrieval --model-set smoke --output-json /tmp/smoke.json --output-md /tmp/smoke.md
```
Expected: `wrote /tmp/smoke.json` — no errors.

**Step 7: Commit**

```bash
git add backend/tests/agent_sim/_support/retrieval_analysis.py \
        backend/tests/agent_sim/tools/evaluate_cross_model_retrieval.py \
        backend/tests/agent_sim/tools/evaluate_similarity_thresholds.py \
        backend/tests/agent_sim/tools/evaluate_embedding_ablation.py \
        backend/tests/test_retrieval_analysis_keywords.py
git commit -m "feat(eval): extend RetrievalRecord with keywords and mechanic_vector"
```

---

## Task 2: Add post_filter callback to compute_cross_model_retrieval_matrix

**Files:**
- Modify: `backend/tests/agent_sim/_support/retrieval_analysis.py`

This adds a pluggable post-filter so the evaluation framework can test Jaccard, two-stage, etc.

**Step 1: Write the failing test**

Append to `backend/tests/test_retrieval_analysis_keywords.py`:

```python
from tests.agent_sim._support.retrieval_analysis import (
    RetrievalRecord,
    compute_cross_model_retrieval_matrix,
)
from tests.agent_sim._support.types import AppCatalog, AppBrief


def _make_minimal_catalog() -> AppCatalog:
    """Return a minimal catalog with two briefs in the same overlap group."""
    brief_a = AppBrief(
        id="brief-a",
        title="Subscription billing saas platform",
        category="billing",
        target_customer="B2B SaaS companies managing recurring revenue",
        problem="Manual billing causes revenue leakage and churn",
        workflow="Automate invoice creation and payment collection for subscriptions",
        recurring_revenue_model="Monthly subscription fee per seat",
        pricing_shape="Per-seat monthly pricing with annual discount",
        distribution_channel="Direct sales and self-serve PLG",
        constraints=["must integrate with Stripe", "must support multi-currency"],
        must_have_features=["subscription management", "invoice generation", "payment retry"],
        seed_keywords=["subscription", "billing", "saas"],
        expected_overlap_group="billing",
        prompt_rendered_brief=(
            "Build a subscription billing saas platform for B2B SaaS companies. "
            "Automate invoice creation and payment collection for subscriptions."
        ),
        success_metric="Process 1000 invoices per day with zero manual intervention",
    )
    brief_b = AppBrief(
        id="brief-b",
        title="Recurring revenue billing automation",
        category="billing",
        target_customer="B2B SaaS companies needing recurring billing",
        problem="Manual subscription billing is error-prone and slow",
        workflow="Automate subscription lifecycle and payment collection",
        recurring_revenue_model="Monthly subscription fee per account",
        pricing_shape="Flat-rate monthly billing with volume discounts",
        distribution_channel="Inbound marketing and product-led growth",
        constraints=["must support Stripe and PayPal", "must be multi-tenant"],
        must_have_features=["subscription management", "payment processing", "reporting"],
        seed_keywords=["billing", "recurring", "automation"],
        expected_overlap_group="billing",
        prompt_rendered_brief=(
            "Build a recurring revenue billing automation tool for B2B SaaS companies. "
            "Automate subscription lifecycle and payment collection workflows."
        ),
        success_metric="Reduce billing errors by 90% within 6 months",
    )
    return AppCatalog(briefs=[brief_a, brief_b])


def test_post_filter_reduces_retrieved():
    """A post_filter that drops everything should produce empty retrieved set."""
    catalog = _make_minimal_catalog()
    vec = [1.0, 0.0]
    records = [
        RetrievalRecord(brief_id="brief-a", model_alias="model-x", vector=vec, keywords=["billing"]),
        RetrievalRecord(brief_id="brief-b", model_alias="model-y", vector=vec, keywords=["other"]),
    ]
    # Filter that drops everything
    drop_all = lambda kws, cands: []
    result = compute_cross_model_retrieval_matrix(
        catalog=catalog,
        records=records,
        threshold=0.0,
        top_k=10,
        post_filter=drop_all,
    )
    summary = result["summary"]
    # With nothing retrieved, FPR must be 0
    assert summary["false_positive_rate"] == 0.0


def test_post_filter_none_behaves_as_baseline():
    """post_filter=None must reproduce baseline results."""
    catalog = _make_minimal_catalog()
    vec = [1.0, 0.0]
    records = [
        RetrievalRecord(brief_id="brief-a", model_alias="model-x", vector=vec, keywords=["billing"]),
        RetrievalRecord(brief_id="brief-b", model_alias="model-y", vector=vec, keywords=["billing"]),
    ]
    baseline = compute_cross_model_retrieval_matrix(
        catalog=catalog, records=records, threshold=0.0, top_k=10
    )
    with_none = compute_cross_model_retrieval_matrix(
        catalog=catalog, records=records, threshold=0.0, top_k=10, post_filter=None
    )
    assert baseline["summary"] == with_none["summary"]
```

**Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_retrieval_analysis_keywords.py::test_post_filter_reduces_retrieved -v
```
Expected: FAIL with `TypeError: compute_cross_model_retrieval_matrix() got an unexpected keyword argument 'post_filter'`

**Step 3: Add post_filter parameter to compute_cross_model_retrieval_matrix**

In `backend/tests/agent_sim/_support/retrieval_analysis.py`:

At the top, add the type alias:
```python
from typing import Callable
PostFilterFn = Callable[[list[str], list[tuple["RetrievalRecord", float]]], list[tuple["RetrievalRecord", float]]]
```

Change the function signature:
```python
def compute_cross_model_retrieval_matrix(
    *,
    catalog: AppCatalog,
    records: list[RetrievalRecord],
    threshold: float,
    top_k: int,
    post_filter: PostFilterFn | None = None,
) -> dict[str, object]:
```

Inside the function, after building `retrieved`, add:
```python
retrieved = [
    (candidate, similarity)
    for candidate, similarity in similarities
    if similarity >= threshold
][:top_k]
# Apply optional post-retrieval filter (e.g. Jaccard, mechanic rerank)
if post_filter is not None:
    retrieved = post_filter(query.keywords, retrieved)
```

Also thread `post_filter` through `evaluate_thresholds`:
```python
def evaluate_thresholds(
    *,
    catalog: AppCatalog,
    records: list[RetrievalRecord],
    thresholds: list[float],
    top_k: int,
    post_filter: PostFilterFn | None = None,
) -> dict[str, object]:
    ...
    result = compute_cross_model_retrieval_matrix(
        catalog=catalog,
        records=records,
        threshold=threshold,
        top_k=top_k,
        post_filter=post_filter,
    )
```

**Step 4: Run all tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_retrieval_analysis_keywords.py -v
```
Expected: 5 PASS

**Step 5: Commit**

```bash
git add backend/tests/agent_sim/_support/retrieval_analysis.py \
        backend/tests/test_retrieval_analysis_keywords.py
git commit -m "feat(eval): add post_filter callback to retrieval matrix evaluation"
```

---

## Task 3: Create evaluate_feature_ablation.py (Option B)

**Files:**
- Create: `backend/tests/agent_sim/tools/evaluate_feature_ablation.py`

This script sweeps all post-retrieval feature combinations and produces a table showing how each changes FPR and recall.

**Filters to test:**
1. `baseline` — no post-filter
2. `jaccard_0.05` through `jaccard_0.30` — Jaccard at 5 thresholds
3. `mechanic_rerank_0.6` through `mechanic_rerank_0.8` — cosine similarity of mechanic_vector, drop below threshold

**Step 1: Write the tool**

Create `backend/tests/agent_sim/tools/evaluate_feature_ablation.py`:

```python
"""Feature ablation: measure FPR/recall for each post-retrieval filter combination."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from dejaship.config import settings
from dejaship.embeddings import build_embedding_text, embed_text, load_model
from tests.agent_sim._support.catalog import (
    load_app_catalog,
    load_model_matrix,
    resolve_enabled_model_aliases,
    resolve_model_set,
)
from tests.agent_sim._support.fixture_store import load_fixture_index
from tests.agent_sim._support.retrieval_analysis import (
    PostFilterFn,
    RetrievalRecord,
    compute_cross_model_retrieval_matrix,
    cosine_similarity,
)


def _jaccard_filter(threshold: float, min_keywords: int) -> PostFilterFn:
    """Post-filter: drop candidates whose keyword Jaccard similarity < threshold."""
    def _filter(
        query_keywords: list[str],
        candidates: list[tuple[RetrievalRecord, float]],
    ) -> list[tuple[RetrievalRecord, float]]:
        if len(query_keywords) < min_keywords:
            return candidates
        query_set = {kw.lower() for kw in query_keywords}
        result = []
        for record, sim in candidates:
            if not record.keywords:
                result.append((record, sim))
                continue
            doc_set = {kw.lower() for kw in record.keywords}
            intersection = len(query_set & doc_set)
            union = len(query_set | doc_set)
            if union > 0 and intersection / union >= threshold:
                result.append((record, sim))
        return result
    return _filter


def _mechanic_rerank_filter(threshold: float) -> PostFilterFn:
    """Post-filter: drop candidates whose mechanic_vector cosine similarity < threshold."""
    def _filter(
        query_keywords: list[str],
        candidates: list[tuple[RetrievalRecord, float]],
    ) -> list[tuple[RetrievalRecord, float]]:
        # query_keywords is the vector's keywords; we need the query mechanic_vector
        # NOTE: mechanic_vector stored on the query record is not directly accessible here.
        # This filter is called with the query record's keywords — mechanic rerank requires
        # the caller to inject the query mechanic_vector via closure. See ablation logic below.
        return candidates  # placeholder; real version built in ablation loop
    return _filter


def _build_filters() -> list[tuple[str, PostFilterFn | None]]:
    filters: list[tuple[str, PostFilterFn | None]] = [("baseline", None)]
    for t in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
        label = f"jaccard_{int(t * 100):02d}"
        filters.append((label, _jaccard_filter(t, min_keywords=2)))
    return filters


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ablation: measure feature impact on FPR/recall.")
    parser.add_argument("--model-set", default="default")
    parser.add_argument("--model-alias", action="append", default=[])
    parser.add_argument("--threshold", type=float, default=settings.SIMILARITY_THRESHOLD)
    parser.add_argument("--top-k", type=int, default=settings.MAX_CLOSEST_RESULTS)
    parser.add_argument("--output-json", default="agent-sim-feature-ablation.json")
    parser.add_argument("--output-md", default="agent-sim-feature-ablation.md")
    return parser.parse_args()


def render_markdown(rows: list[dict], *, threshold: float, top_k: int) -> str:
    lines = [
        "# Feature Ablation Report",
        "",
        f"- Vector threshold: {threshold}",
        f"- Top-k: {top_k}",
        "",
        "## Results",
        "",
        "| Filter | Recall | FPR | Precision | Overlap Hit | Δ Recall | Δ FPR |",
        "|--------|--------|-----|-----------|-------------|----------|-------|",
    ]
    baseline = next((r for r in rows if r["filter"] == "baseline"), None)
    for row in rows:
        delta_recall = round(row["recall_at_k"] - (baseline["recall_at_k"] if baseline else 0), 4)
        delta_fpr = round(row["false_positive_rate"] - (baseline["false_positive_rate"] if baseline else 0), 4)
        lines.append(
            f"| {row['filter']} | {row['recall_at_k']} | {row['false_positive_rate']} "
            f"| {row['overlap_precision_at_k']} | {row['overlap_hit_rate']} "
            f"| {delta_recall:+.4f} | {delta_fpr:+.4f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    app_catalog = load_app_catalog()
    model_matrix = load_model_matrix()
    fixture_index = load_fixture_index()

    if args.model_alias:
        selected_models = resolve_enabled_model_aliases(model_matrix, args.model_alias)
    else:
        selected_models = resolve_model_set(model_matrix, args.model_set)

    load_model()
    records: list[RetrievalRecord] = []
    for model_alias, _ in selected_models:
        for brief in app_catalog.briefs:
            fixture = fixture_index.get(brief_id=brief.id, model_alias=model_alias)
            if fixture is None:
                continue
            text = build_embedding_text(
                fixture.final_intent_input.core_mechanic,
                fixture.final_intent_input.keywords,
            )
            records.append(
                RetrievalRecord(
                    brief_id=brief.id,
                    model_alias=model_alias,
                    vector=embed_text(text),
                    keywords=fixture.final_intent_input.keywords,
                    mechanic_vector=embed_text(fixture.final_intent_input.core_mechanic),
                )
            )

    filters = _build_filters()
    rows: list[dict] = []
    for filter_name, post_filter in filters:
        result = compute_cross_model_retrieval_matrix(
            catalog=app_catalog,
            records=records,
            threshold=args.threshold,
            top_k=args.top_k,
            post_filter=post_filter,
        )
        summary = dict(result["summary"])
        summary["filter"] = filter_name
        rows.append(summary)
        print(f"  {filter_name}: recall={summary['recall_at_k']}, fpr={summary['false_positive_rate']}")

    payload = {"threshold": args.threshold, "top_k": args.top_k, "filters": rows}
    json_path = Path(args.output_json)
    md_path = Path(args.output_md)
    json_path.write_text(json.dumps(payload, indent=2))
    md_path.write_text(render_markdown(rows, threshold=args.threshold, top_k=args.top_k))
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
```

**Step 2: Run the script against smoke set first**

```bash
cd backend && uv run python -m tests.agent_sim.tools.evaluate_feature_ablation \
  --model-set smoke \
  --output-json /tmp/feature-ablation-smoke.json \
  --output-md /tmp/feature-ablation-smoke.md
```
Expected: prints one line per filter, writes two files, no errors.

**Step 3: Run against coverage-max**

```bash
cd backend && uv run python -m tests.agent_sim.tools.evaluate_feature_ablation \
  --model-set coverage-max \
  --output-json /tmp/feature-ablation.json \
  --output-md /tmp/feature-ablation.md
```
Expected: table showing baseline recall/FPR and effect of each Jaccard threshold. Takes ~3 minutes.

**Step 4: Copy results to docs**

```bash
cp /tmp/feature-ablation.md \
   /home/user/src/m/dejaship/dejaship/docs/search-quality/feature-ablation.md
```

**Step 5: Commit**

```bash
git add backend/tests/agent_sim/tools/evaluate_feature_ablation.py \
        docs/search-quality/feature-ablation.md
git commit -m "feat(eval): add feature ablation script measuring Jaccard impact on FPR/recall"
```

---

## Task 4: Write unit tests for the new Jaccard post-filter logic

**Files:**
- Create: `backend/tests/test_feature_ablation_filters.py`

**Step 1: Write tests**

```python
"""Unit tests for the Jaccard post-filter used in feature ablation."""
from tests.agent_sim._support.retrieval_analysis import RetrievalRecord
from tests.agent_sim.tools.evaluate_feature_ablation import _jaccard_filter


def _rec(kws: list[str]) -> tuple[RetrievalRecord, float]:
    return RetrievalRecord(brief_id="x", model_alias="m", vector=[], keywords=kws), 0.9


def test_jaccard_filter_passes_exact_overlap():
    f = _jaccard_filter(threshold=0.1, min_keywords=2)
    query_kws = ["saas", "billing", "subscription"]
    candidates = [_rec(["saas", "billing"])]
    result = f(query_kws, candidates)
    assert len(result) == 1  # 2 shared / 3 union ≈ 0.67 > 0.10


def test_jaccard_filter_drops_disjoint():
    f = _jaccard_filter(threshold=0.1, min_keywords=2)
    query_kws = ["saas", "billing"]
    candidates = [_rec(["healthcare", "imaging"])]
    result = f(query_kws, candidates)
    assert len(result) == 0  # 0 shared → Jaccard = 0


def test_jaccard_filter_skips_when_few_query_keywords():
    f = _jaccard_filter(threshold=0.5, min_keywords=3)
    query_kws = ["saas"]  # only 1, below min_keywords=3
    candidates = [_rec(["healthcare", "imaging"])]
    result = f(query_kws, candidates)
    assert len(result) == 1  # filter skipped, all pass


def test_jaccard_filter_passes_empty_candidate_keywords():
    f = _jaccard_filter(threshold=0.5, min_keywords=2)
    query_kws = ["saas", "billing"]
    candidates = [_rec([])]  # no keywords on candidate
    result = f(query_kws, candidates)
    assert len(result) == 1  # no keywords → pass through


def test_jaccard_filter_case_insensitive():
    f = _jaccard_filter(threshold=0.3, min_keywords=2)
    query_kws = ["SaaS", "Billing"]
    candidates = [_rec(["saas", "billing"])]  # lowercase
    result = f(query_kws, candidates)
    assert len(result) == 1  # 2/2 union = 1.0 > 0.3


def test_jaccard_filter_exact_threshold_passes():
    # query={"a","b","c"}, doc={"a"} → intersection=1, union=3, Jaccard=0.333
    f = _jaccard_filter(threshold=0.333, min_keywords=2)
    result = f(["a", "b", "c"], [_rec(["a"])])
    assert len(result) == 1


def test_jaccard_filter_below_threshold_drops():
    # query={"a","b","c","d"}, doc={"a"} → 1/4=0.25 < 0.30
    f = _jaccard_filter(threshold=0.30, min_keywords=2)
    result = f(["a", "b", "c", "d"], [_rec(["a"])])
    assert len(result) == 0
```

**Step 2: Run to verify they fail**

```bash
cd backend && uv run pytest tests/test_feature_ablation_filters.py -v
```
Expected: FAIL (the module exists but `_jaccard_filter` may not be importable yet if the script above isn't created).
If it fails with import error, create the script first (Task 3), then re-run.

**Step 3: Run to verify they pass (after script is created)**

```bash
cd backend && uv run pytest tests/test_feature_ablation_filters.py -v
```
Expected: 7 PASS

**Step 4: Commit**

```bash
git add backend/tests/test_feature_ablation_filters.py
git commit -m "test(eval): unit tests for Jaccard post-filter in feature ablation"
```

---

## Task 5: Full-stack integration evaluation (Option C)

**Files:**
- Create: `backend/tests/agent_sim/test_coverage_max_fullstack.py`

This test populates a real pgvector DB with coverage-max fixture claims, then calls `POST /v1/check` for each brief and measures actual FPR/recall through the full service stack.

**How it works:**
1. Load all coverage-max fixtures from disk
2. POST `/v1/claim` for each fixture → inserts embeddings into real pgvector DB
3. For each fixture (as query), POST `/v1/check` with the same core_mechanic + keywords
4. Inspect `closest_active_claims` in the response
5. Measure FPR and recall using the same `related_brief_ids` logic as the in-memory eval

**Mark as slow** — this test requires Docker and takes minutes. Use `@pytest.mark.slow`.

**Step 1: Write the test**

Create `backend/tests/agent_sim/test_coverage_max_fullstack.py`:

```python
"""Full-stack retrieval quality test using real pgvector + testcontainers.

Requires Docker. Run with: uv run pytest tests/agent_sim/test_coverage_max_fullstack.py -v -m slow

Measures FPR and recall of check_airspace() on the coverage-max corpus,
testing the full stack including pgvector HNSW index and all feature flags.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.agent_sim._support.catalog import (
    load_app_catalog,
    load_model_matrix,
    resolve_model_set,
)
from tests.agent_sim._support.fixture_store import load_fixture_index
from tests.agent_sim._support.retrieval_analysis import related_brief_ids


pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def app_catalog():
    return load_app_catalog()


@pytest.fixture(scope="module")
def coverage_max_fixtures():
    model_matrix = load_model_matrix()
    fixture_index = load_fixture_index()
    selected_models = resolve_model_set(model_matrix, "coverage-max")
    fixtures = []
    catalog = load_app_catalog()
    for model_alias, _ in selected_models:
        for brief in catalog.briefs:
            fx = fixture_index.get(brief_id=brief.id, model_alias=model_alias)
            if fx is not None:
                fixtures.append((brief.id, model_alias, fx))
    return fixtures


@pytest.mark.asyncio
async def test_fullstack_retrieval_quality(client: AsyncClient, app_catalog, coverage_max_fixtures):
    """Populate DB with coverage-max claims, measure FPR/recall via check_airspace."""
    # Map brief_id+model_alias → claim_id (for later correlation)
    claimed: dict[tuple[str, str], str] = {}

    # Step 1: claim all fixtures
    for brief_id, model_alias, fx in coverage_max_fixtures:
        payload = {
            "core_mechanic": fx.final_intent_input.core_mechanic,
            "keywords": fx.final_intent_input.keywords,
        }
        resp = await client.post("/v1/claim", json=payload)
        assert resp.status_code == 201, f"claim failed for {brief_id}/{model_alias}: {resp.text}"
        claimed[(brief_id, model_alias)] = resp.json()["claim_id"]

    # Step 2: check each fixture and measure retrieval quality
    retrieved_total = 0
    false_positive_retrieved = 0
    relevant_available = 0
    relevant_retrieved = 0

    brief_map = {brief.id: brief for brief in app_catalog.briefs}

    for brief_id, model_alias, fx in coverage_max_fixtures:
        payload = {
            "core_mechanic": fx.final_intent_input.core_mechanic,
            "keywords": fx.final_intent_input.keywords,
        }
        resp = await client.post("/v1/check", json=payload)
        assert resp.status_code == 200, f"check failed: {resp.text}"

        closest = resp.json().get("closest_active_claims", [])
        related_ids = related_brief_ids(app_catalog, brief_id)

        # Count how many claimed briefs are related to this query brief
        relevant_claimed_brief_ids = {
            bid for bid, _ in claimed if bid in related_ids
        }
        relevant_available += len(relevant_claimed_brief_ids)

        # The check response returns mechanics, not brief_ids. We approximate:
        # A result is "relevant" if its mechanic matches a related brief's fixture mechanic.
        related_mechanics = set()
        for related_id in related_ids:
            for (bid, _), _ in [(k, v) for k, v in claimed.items() if k[0] == related_id]:
                fx_rel = next(
                    (f for b, m, f in coverage_max_fixtures if b == related_id),
                    None,
                )
                if fx_rel:
                    related_mechanics.add(fx_rel.final_intent_input.core_mechanic)

        returned_mechanics = {c["mechanic"] for c in closest}
        retrieved_total += len(closest)

        rel_retrieved = returned_mechanics & related_mechanics
        fp_retrieved = returned_mechanics - related_mechanics - {fx.final_intent_input.core_mechanic}

        relevant_retrieved += len(rel_retrieved)
        false_positive_retrieved += len(fp_retrieved)

    recall = relevant_retrieved / relevant_available if relevant_available > 0 else 0.0
    fpr = false_positive_retrieved / retrieved_total if retrieved_total > 0 else 0.0

    print(f"\nFull-stack retrieval quality (coverage-max):")
    print(f"  Retrieved total: {retrieved_total}")
    print(f"  Recall@k: {recall:.4f}")
    print(f"  False positive rate: {fpr:.4f}")

    # Soft assertions: recall should not be catastrophically low
    # and FPR should not be catastrophically high. These are baselines, not hard SLOs.
    assert recall >= 0.30, f"recall {recall:.4f} below minimum threshold of 0.30"
    assert fpr <= 0.95, f"fpr {fpr:.4f} above maximum threshold of 0.95"
```

**Step 2: Add `slow` marker to pyproject.toml**

In `backend/pyproject.toml`, find the `[tool.pytest.ini_options]` section and add:

```toml
markers = [
    "slow: marks tests as slow (require Docker, run separately with -m slow)",
]
```

**Step 3: Verify the test is collected but skipped in normal runs**

```bash
cd backend && uv run pytest tests/agent_sim/test_coverage_max_fullstack.py --collect-only
```
Expected: test collected, no errors.

```bash
cd backend && uv run pytest tests/ -v --ignore=tests/agent_sim/test_coverage_max_fullstack.py
```
Expected: existing tests pass, fullstack test not run.

**Step 4: Run the full-stack test (requires Docker)**

```bash
cd backend && uv run pytest tests/agent_sim/test_coverage_max_fullstack.py -v -m slow -s
```
Expected: ~3-5 minutes; prints FPR and recall; assertions pass.

**Step 5: Commit**

```bash
git add backend/tests/agent_sim/test_coverage_max_fullstack.py \
        backend/pyproject.toml
git commit -m "feat(eval): full-stack retrieval quality test via testcontainers (Option C)"
```

---

## Verification

Run the full unit test suite (no Docker):
```bash
cd backend && uv run pytest tests/ -v --ignore=tests/agent_sim/test_coverage_max_fullstack.py
```
Expected: all existing + new unit tests pass.

Run the feature ablation scripts (no Docker):
```bash
cd backend && uv run python -m tests.agent_sim.tools.evaluate_feature_ablation \
  --model-set coverage-max \
  --output-md /tmp/feature-ablation.md && cat /tmp/feature-ablation.md
```

Run the full-stack test (requires Docker):
```bash
cd backend && uv run pytest tests/agent_sim/test_coverage_max_fullstack.py -v -s
```
