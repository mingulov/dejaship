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
    evaluate_thresholds,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sweep similarity thresholds against stored agent-sim fixtures.")
    parser.add_argument("--model-set", default="default")
    parser.add_argument("--model-alias", action="append", default=[])
    parser.add_argument("--start", type=float, default=0.55)
    parser.add_argument("--stop", type=float, default=0.9)
    parser.add_argument("--step", type=float, default=0.05)
    parser.add_argument("--top-k", type=int, default=settings.MAX_CLOSEST_RESULTS)
    parser.add_argument("--output-json", default="agent-sim-threshold-sweep.json")
    parser.add_argument("--output-md", default="agent-sim-threshold-sweep.md")
    return parser.parse_args()


def _float_range(start: float, stop: float, step: float) -> list[float]:
    values: list[float] = []
    current = start
    while current <= stop + 1e-9:
        values.append(round(current, 4))
        current += step
    return values


def render_markdown(result: dict[str, object]) -> str:
    lines = [
        "# Similarity Threshold Sweep",
        "",
        f"- Recommended threshold: {result['recommended_threshold']}",
        f"- Recommendation basis: {result['recommendation_basis']}",
        "",
        "## Thresholds",
    ]
    for evaluation in result["evaluations"]:
        lines.append(
            f"- threshold={evaluation['threshold']}: balanced_score={evaluation['balanced_score']}, "
            f"exact_top1_rate={evaluation['exact_top1_rate']}, overlap_hit_rate={evaluation['overlap_hit_rate']}, "
            f"precision_at_k={evaluation['overlap_precision_at_k']}, recall_at_k={evaluation['recall_at_k']}, "
            f"false_positive_rate={evaluation['false_positive_rate']}, avg_first_relevant_rank={evaluation['average_first_relevant_rank']}"
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
                )
            )

    result = evaluate_thresholds(
        catalog=app_catalog,
        records=records,
        thresholds=_float_range(args.start, args.stop, args.step),
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
