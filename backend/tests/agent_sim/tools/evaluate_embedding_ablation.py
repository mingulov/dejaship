from __future__ import annotations

import argparse
import json
from pathlib import Path

from dejaship.config import settings
from dejaship.embeddings import embed_text, load_model
from tests.agent_sim._support.catalog import (
    load_app_catalog,
    load_model_matrix,
    resolve_enabled_model_aliases,
    resolve_model_set,
)
from tests.agent_sim._support.embedding_variants import build_variant_text, supported_embedding_variants
from tests.agent_sim._support.fixture_store import load_fixture_index
from tests.agent_sim._support.retrieval_analysis import (
    RetrievalRecord,
    compute_cross_model_retrieval_matrix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate embedding-text variants and keyword-repeat sensitivity.")
    parser.add_argument("--model-set", default="default")
    parser.add_argument("--model-alias", action="append", default=[])
    parser.add_argument("--variant", action="append", default=[])
    parser.add_argument("--keyword-repeat", action="append", type=int, default=[])
    parser.add_argument("--threshold", type=float, default=settings.SIMILARITY_THRESHOLD)
    parser.add_argument("--top-k", type=int, default=settings.MAX_CLOSEST_RESULTS)
    parser.add_argument("--output-json", default="agent-sim-embedding-ablation.json")
    parser.add_argument("--output-md", default="agent-sim-embedding-ablation.md")
    return parser.parse_args()


def render_markdown(result: dict[str, object]) -> str:
    lines = [
        "# Embedding Text Ablation",
        "",
        f"- Threshold: {result['threshold']}",
        f"- Top-k: {result['top_k']}",
        "",
        "## Variants",
    ]
    for row in result["variants"]:
        lines.append(
            f"- {row['variant']} (keyword_repeat={row['keyword_repeat']}): exact_top1_rate={row['exact_top1_rate']}, "
            f"overlap_hit_rate={row['overlap_hit_rate']}, precision_at_k={row['overlap_precision_at_k']}, "
            f"recall_at_k={row['recall_at_k']}, false_positive_rate={row['false_positive_rate']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    app_catalog = load_app_catalog()
    brief_map = {brief.id: brief for brief in app_catalog.briefs}
    model_matrix = load_model_matrix()
    fixture_index = load_fixture_index()
    if args.model_alias:
        selected_models = resolve_enabled_model_aliases(model_matrix, args.model_alias)
    else:
        selected_models = resolve_model_set(model_matrix, args.model_set)

    variants = args.variant or supported_embedding_variants()
    keyword_repeats = args.keyword_repeat or [1, settings.KEYWORD_REPEAT, 3, 4]

    load_model()
    rows: list[dict[str, object]] = []
    for variant in variants:
        active_repeats = keyword_repeats if variant == "current_combined" else [settings.KEYWORD_REPEAT]
        for keyword_repeat in active_repeats:
            records: list[RetrievalRecord] = []
            for model_alias, _ in selected_models:
                for brief in app_catalog.briefs:
                    fixture = fixture_index.get(brief_id=brief.id, model_alias=model_alias)
                    if fixture is None:
                        continue
                    text = build_variant_text(
                        variant=variant,
                        core_mechanic=fixture.final_intent_input.core_mechanic,
                        keywords=fixture.final_intent_input.keywords,
                        brief=brief_map[brief.id],
                        keyword_repeat=keyword_repeat,
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
            summary = dict(result["summary"])
            summary["variant"] = variant
            summary["keyword_repeat"] = keyword_repeat
            rows.append(summary)

    payload = {
        "threshold": args.threshold,
        "top_k": args.top_k,
        "variants": rows,
    }
    json_path = Path(args.output_json)
    md_path = Path(args.output_md)
    json_path.write_text(json.dumps(payload, indent=2))
    md_path.write_text(render_markdown(payload))
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
