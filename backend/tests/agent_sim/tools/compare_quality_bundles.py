from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two agent-sim quality bundles.")
    parser.add_argument("baseline", help="Path to the baseline quality bundle directory")
    parser.add_argument("candidate", help="Path to the candidate quality bundle directory")
    parser.add_argument("--output-json", default="agent-sim-bundle-diff.json")
    parser.add_argument("--output-md", default="agent-sim-bundle-diff.md")
    return parser.parse_args()


def _load_json(bundle_dir: Path, filename: str) -> dict:
    return json.loads((bundle_dir / filename).read_text())


def _metric_delta(candidate: float, baseline: float) -> float:
    return round(candidate - baseline, 4)


def _read_bundle(bundle_dir: Path) -> dict[str, dict]:
    return {
        "manifest": _load_json(bundle_dir, "manifest.json"),
        "swarm": _load_json(bundle_dir, "swarm_report.json"),
        "cross_model": _load_json(bundle_dir, "cross_model_retrieval.json"),
        "threshold_sweep": _load_json(bundle_dir, "threshold_sweep.json"),
        "embedding_ablation": _load_json(bundle_dir, "embedding_ablation.json"),
    }


def _best_ablation_variant(bundle: dict) -> dict:
    variants = bundle["embedding_ablation"]["variants"]
    return max(
        variants,
        key=lambda row: (
            row["exact_top1_rate"]
            + row["overlap_hit_rate"]
            + row["overlap_precision_at_k"]
            + row["recall_at_k"]
            - row["false_positive_rate"]
        ),
    )


def build_comparison(baseline_bundle: dict, candidate_bundle: dict) -> dict[str, object]:
    baseline_swarm = baseline_bundle["swarm"]["report"]["metrics"]
    candidate_swarm = candidate_bundle["swarm"]["report"]["metrics"]
    baseline_cross = baseline_bundle["cross_model"]["summary"]
    candidate_cross = candidate_bundle["cross_model"]["summary"]

    key_metrics = {
        "swarm_overlap_hit_rate": _metric_delta(
            candidate_swarm["overlap_hit_rate"], baseline_swarm["overlap_hit_rate"]
        ),
        "swarm_overlap_precision": _metric_delta(
            candidate_swarm["overlap_precision"], baseline_swarm["overlap_precision"]
        ),
        "swarm_duplicate_overlap_group_rate": _metric_delta(
            candidate_swarm["duplicate_overlap_group_rate"], baseline_swarm["duplicate_overlap_group_rate"]
        ),
        "cross_exact_top1_rate": _metric_delta(
            candidate_cross["exact_top1_rate"], baseline_cross["exact_top1_rate"]
        ),
        "cross_overlap_hit_rate": _metric_delta(
            candidate_cross["overlap_hit_rate"], baseline_cross["overlap_hit_rate"]
        ),
        "cross_precision_at_k": _metric_delta(
            candidate_cross["overlap_precision_at_k"], baseline_cross["overlap_precision_at_k"]
        ),
        "cross_recall_at_k": _metric_delta(
            candidate_cross["recall_at_k"], baseline_cross["recall_at_k"]
        ),
        "cross_false_positive_rate": _metric_delta(
            candidate_cross["false_positive_rate"], baseline_cross["false_positive_rate"]
        ),
    }

    baseline_recommended_threshold = baseline_bundle["threshold_sweep"]["recommended_threshold"]
    candidate_recommended_threshold = candidate_bundle["threshold_sweep"]["recommended_threshold"]
    baseline_best_variant = _best_ablation_variant(baseline_bundle)
    candidate_best_variant = _best_ablation_variant(candidate_bundle)

    summary_flags: list[str] = []
    if key_metrics["cross_overlap_hit_rate"] > 0 and key_metrics["cross_false_positive_rate"] <= 0:
        summary_flags.append("candidate-improves-overlap-without-more-noise")
    if key_metrics["cross_false_positive_rate"] > 0 and key_metrics["cross_overlap_hit_rate"] <= 0:
        summary_flags.append("candidate-adds-noise-without-overlap-benefit")
    if key_metrics["cross_exact_top1_rate"] < 0:
        summary_flags.append("candidate-regresses-exact-retrieval")

    return {
        "baseline": {
            "git_sha": baseline_bundle["manifest"]["git_sha"],
            "similarity_threshold": baseline_bundle["manifest"]["similarity_threshold"],
            "recommended_threshold": baseline_recommended_threshold,
            "best_ablation_variant": baseline_best_variant,
        },
        "candidate": {
            "git_sha": candidate_bundle["manifest"]["git_sha"],
            "similarity_threshold": candidate_bundle["manifest"]["similarity_threshold"],
            "recommended_threshold": candidate_recommended_threshold,
            "best_ablation_variant": candidate_best_variant,
        },
        "metric_deltas": key_metrics,
        "summary_flags": summary_flags,
    }


def render_markdown(result: dict[str, object]) -> str:
    lines = [
        "# Agent Sim Bundle Comparison",
        "",
        "## Baseline",
        f"- Git SHA: {result['baseline']['git_sha']}",
        f"- Similarity threshold: {result['baseline']['similarity_threshold']}",
        f"- Recommended threshold: {result['baseline']['recommended_threshold']}",
        f"- Best ablation variant: {result['baseline']['best_ablation_variant']['variant']} "
        f"(keyword_repeat={result['baseline']['best_ablation_variant']['keyword_repeat']})",
        "",
        "## Candidate",
        f"- Git SHA: {result['candidate']['git_sha']}",
        f"- Similarity threshold: {result['candidate']['similarity_threshold']}",
        f"- Recommended threshold: {result['candidate']['recommended_threshold']}",
        f"- Best ablation variant: {result['candidate']['best_ablation_variant']['variant']} "
        f"(keyword_repeat={result['candidate']['best_ablation_variant']['keyword_repeat']})",
        "",
        "## Metric Deltas",
    ]
    for key, value in result["metric_deltas"].items():
        lines.append(f"- {key}: {value:+.4f}")
    lines.extend(["", "## Summary Flags"])
    if result["summary_flags"]:
        lines.extend(f"- {flag}" for flag in result["summary_flags"])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    baseline_dir = Path(args.baseline)
    candidate_dir = Path(args.candidate)
    result = build_comparison(_read_bundle(baseline_dir), _read_bundle(candidate_dir))
    Path(args.output_json).write_text(json.dumps(result, indent=2))
    Path(args.output_md).write_text(render_markdown(result))
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")


if __name__ == "__main__":
    main()
