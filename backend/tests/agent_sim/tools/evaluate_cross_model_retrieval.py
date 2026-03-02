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
    RetrievalRecord,
    compute_cross_model_retrieval_matrix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate whether claims produced by one model are discoverable by other models."
    )
    parser.add_argument("--model-set", default="default", help="Model set from model_matrix.yaml")
    parser.add_argument("--model-alias", action="append", default=[], help="Specific enabled model alias to include")
    parser.add_argument("--threshold", type=float, default=settings.SIMILARITY_THRESHOLD, help="Cosine similarity threshold")
    parser.add_argument("--top-k", type=int, default=settings.MAX_CLOSEST_RESULTS, help="Maximum retrieved claims per query")
    parser.add_argument(
        "--output-json",
        default="agent-sim-cross-model-retrieval.json",
        help="Path to JSON output",
    )
    parser.add_argument(
        "--output-md",
        default="agent-sim-cross-model-retrieval.md",
        help="Path to Markdown output",
    )
    return parser.parse_args()


def render_markdown(result: dict[str, object]) -> str:
    summary = result["summary"]
    matrix = result["matrix"]
    lines = [
        "# Cross-Model Retrieval Report",
        "",
        "## Summary",
        f"- Models: {summary['model_count']}",
        f"- Model pairs: {summary['pair_count']}",
        f"- Exact top-1 retrieval rate: {summary['exact_top1_rate']}",
        f"- Exact threshold retrieval rate: {summary['exact_threshold_rate']}",
        f"- Overlap hit rate: {summary['overlap_hit_rate']}",
        f"- Overlap precision@k: {summary['overlap_precision_at_k']}",
        f"- Recall@k: {summary['recall_at_k']}",
        f"- False positive rate: {summary['false_positive_rate']}",
        f"- Avg first relevant rank: {summary['average_first_relevant_rank']}",
        f"- Avg exact top-1 asymmetry gap: {summary['average_exact_top1_gap']}",
        f"- Avg overlap-hit asymmetry gap: {summary['average_overlap_hit_gap']}",
        "",
        "## Pair Matrix",
    ]
    for query_model, row in matrix.items():
        lines.append(f"### Query Model: {query_model}")
        for claim_model, pair in row.items():
            lines.append(
                f"- claim={claim_model}: exact_top1_rate={pair['exact_top1_rate']}, "
                f"exact_threshold_rate={pair['exact_threshold_rate']}, overlap_hit_rate={pair['overlap_hit_rate']}, "
                f"overlap_precision_at_k={pair['overlap_precision_at_k']}, recall_at_k={pair['recall_at_k']}, "
                f"false_positive_rate={pair['false_positive_rate']}, avg_first_relevant_rank={pair['average_first_relevant_rank']}, "
                f"queries={pair['query_count']}"
            )
        lines.append("")
    if result["asymmetry"]:
        lines.append("## Asymmetry")
        for row in result["asymmetry"]:
            lines.append(
                f"- {row['model_a']} vs {row['model_b']}: exact_top1_gap={row['exact_top1_gap']}, "
                f"overlap_hit_gap={row['overlap_hit_gap']}, precision_gap={row['precision_gap']}"
            )
    return "\n".join(lines).rstrip() + "\n"


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
                )
            )

    result = compute_cross_model_retrieval_matrix(
        catalog=app_catalog,
        records=records,
        threshold=args.threshold,
        top_k=args.top_k,
    )
    json_path = Path(args.output_json)
    md_path = Path(args.output_md)
    json_path.write_text(json.dumps(result, indent=2))
    md_path.write_text(render_markdown(result))
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
