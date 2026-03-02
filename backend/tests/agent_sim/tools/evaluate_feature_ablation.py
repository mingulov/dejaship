"""Feature ablation: measure FPR/recall impact of each post-retrieval filter.

Sweeps Jaccard thresholds and reports how each changes recall and FPR vs. baseline.

Usage:
    uv run python -m tests.agent_sim.tools.evaluate_feature_ablation \\
        --model-set coverage-max \\
        --output-json /tmp/feature-ablation.json \\
        --output-md /tmp/feature-ablation.md
"""
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
        "| Filter | Recall@k | FPR | Precision@k | Overlap Hit | Δ Recall | Δ FPR |",
        "|--------|----------|-----|-------------|-------------|----------|-------|",
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

    print(f"Loading embeddings for {len(selected_models)} models × {len(app_catalog.briefs)} briefs...")
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
    print(f"Embedded {len(records)} records.")

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
        summary = dict(result["summary"])  # type: ignore[arg-type]
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
