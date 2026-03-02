from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Callable, cast

from tests.agent_sim._support.types import AppCatalog

PostFilterFn = Callable[
    ["RetrievalRecord", list[tuple["RetrievalRecord", float]]],
    list[tuple["RetrievalRecord", float]],
]


@dataclass(slots=True)
class RetrievalRecord:
    brief_id: str
    model_alias: str
    vector: list[float]
    keywords: list[str] = field(default_factory=list)
    mechanic_vector: list[float] = field(default_factory=list)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimensionality")
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    return dot / (left_norm * right_norm)


def related_brief_ids(catalog: AppCatalog, brief_id: str) -> set[str]:
    brief_map = {brief.id: brief for brief in catalog.briefs}
    brief = brief_map[brief_id]
    valid_groups = {brief.expected_overlap_group, *brief.adjacent_overlap_groups}
    return {
        candidate.id
        for candidate in catalog.briefs
        if candidate.id != brief_id
        and (
            candidate.expected_overlap_group in valid_groups
            or brief.expected_overlap_group in candidate.adjacent_overlap_groups
        )
    }


def _safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def compute_cross_model_retrieval_matrix(
    *,
    catalog: AppCatalog,
    records: list[RetrievalRecord],
    threshold: float,
    top_k: int,
    post_filter: PostFilterFn | None = None,
) -> dict[str, object]:
    by_model: dict[str, list[RetrievalRecord]] = {}
    for record in records:
        by_model.setdefault(record.model_alias, []).append(record)

    matrix: dict[str, dict[str, dict[str, float | int]]] = {}
    asymmetry_rows: list[dict[str, float | str]] = []
    global_counts = {
        "exact_queries": 0,
        "exact_top1_hits": 0,
        "exact_threshold_hits": 0,
        "overlap_queries": 0,
        "overlap_hits": 0,
        "retrieved_total": 0,
        "relevant_retrieved_total": 0,
        "relevant_available_total": 0,
        "false_positive_retrieved_total": 0,
        "first_relevant_rank_total": 0,
        "first_relevant_rank_count": 0,
    }

    for query_model, query_records in sorted(by_model.items()):
        row: dict[str, dict[str, float | int]] = {}
        for claim_model, claim_records in sorted(by_model.items()):
            if query_model == claim_model:
                continue

            pair = cast(dict[str, int | float], {
                "query_count": 0,
                "exact_queries": 0,
                "exact_top1_hits": 0,
                "exact_threshold_hits": 0,
                "overlap_queries": 0,
                "overlap_hits": 0,
                "retrieved_total": 0,
                "relevant_retrieved_total": 0,
                "relevant_available_total": 0,
                "false_positive_retrieved_total": 0,
                "first_relevant_rank_total": 0,
                "first_relevant_rank_count": 0,
            })
            claim_by_brief = {record.brief_id: record for record in claim_records}

            for query in query_records:
                similarities = sorted(
                    (
                        (candidate, cosine_similarity(query.vector, candidate.vector))
                        for candidate in claim_records
                    ),
                    key=lambda item: item[1],
                    reverse=True,
                )
                retrieved = [
                    (candidate, similarity)
                    for candidate, similarity in similarities
                    if similarity >= threshold
                ][:top_k]
                if post_filter is not None:
                    retrieved = post_filter(query, retrieved)
                related_ids = related_brief_ids(catalog, query.brief_id)
                exact_target = claim_by_brief.get(query.brief_id)
                relevant_ids = set(related_ids)
                if exact_target is not None:
                    relevant_ids.add(query.brief_id)

                pair["query_count"] += 1
                if exact_target is not None:
                    pair["exact_queries"] += 1
                    exact_similarity = cosine_similarity(query.vector, exact_target.vector)
                    if exact_similarity >= threshold:
                        pair["exact_threshold_hits"] += 1
                    if retrieved and retrieved[0][0].brief_id == query.brief_id:
                        pair["exact_top1_hits"] += 1

                if related_ids:
                    pair["overlap_queries"] += 1
                    pair["relevant_available_total"] += len(
                        [candidate for candidate in claim_records if candidate.brief_id in related_ids]
                    )
                    relevant_retrieved = [candidate for candidate, _ in retrieved if candidate.brief_id in related_ids]
                    if relevant_retrieved:
                        pair["overlap_hits"] += 1
                    first_relevant_rank = next(
                        (
                            rank
                            for rank, (candidate, _) in enumerate(similarities, start=1)
                            if candidate.brief_id in related_ids
                        ),
                        None,
                    )
                    if first_relevant_rank is not None:
                        pair["first_relevant_rank_total"] += first_relevant_rank
                        pair["first_relevant_rank_count"] += 1
                    pair["retrieved_total"] += len(retrieved)
                    pair["relevant_retrieved_total"] += len(relevant_retrieved)

                pair["false_positive_retrieved_total"] += len(
                    [candidate for candidate, _ in retrieved if candidate.brief_id not in relevant_ids]
                )

            pair["exact_top1_rate"] = _safe_rate(pair["exact_top1_hits"], pair["exact_queries"])
            pair["exact_threshold_rate"] = _safe_rate(pair["exact_threshold_hits"], pair["exact_queries"])
            pair["overlap_hit_rate"] = _safe_rate(pair["overlap_hits"], pair["overlap_queries"])
            pair["overlap_precision_at_k"] = _safe_rate(
                pair["relevant_retrieved_total"], pair["retrieved_total"]
            )
            pair["recall_at_k"] = _safe_rate(
                pair["relevant_retrieved_total"], pair["relevant_available_total"]
            )
            pair["false_positive_rate"] = _safe_rate(
                pair["false_positive_retrieved_total"], pair["retrieved_total"]
            )
            pair["average_first_relevant_rank"] = _safe_rate(
                pair["first_relevant_rank_total"], pair["first_relevant_rank_count"]
            )

            row[claim_model] = pair
            for key in global_counts:
                global_counts[key] += int(pair[key])

        matrix[query_model] = row

    processed_pairs: set[tuple[str, str]] = set()
    for query_model, row in matrix.items():
        for claim_model, pair in row.items():
            if (claim_model, query_model) in processed_pairs:
                continue
            reverse = matrix.get(claim_model, {}).get(query_model)
            if reverse is None:
                continue
            asymmetry_rows.append(
                {
                    "model_a": query_model,
                    "model_b": claim_model,
                    "exact_top1_gap": round(abs(pair["exact_top1_rate"] - reverse["exact_top1_rate"]), 4),
                    "overlap_hit_gap": round(abs(pair["overlap_hit_rate"] - reverse["overlap_hit_rate"]), 4),
                    "precision_gap": round(
                        abs(pair["overlap_precision_at_k"] - reverse["overlap_precision_at_k"]), 4
                    ),
                }
            )
            processed_pairs.add((query_model, claim_model))

    summary = {
        "model_count": len(by_model),
        "pair_count": sum(len(row) for row in matrix.values()),
        "exact_top1_rate": _safe_rate(global_counts["exact_top1_hits"], global_counts["exact_queries"]),
        "exact_threshold_rate": _safe_rate(global_counts["exact_threshold_hits"], global_counts["exact_queries"]),
        "overlap_hit_rate": _safe_rate(global_counts["overlap_hits"], global_counts["overlap_queries"]),
        "overlap_precision_at_k": _safe_rate(
            global_counts["relevant_retrieved_total"], global_counts["retrieved_total"]
        ),
        "recall_at_k": _safe_rate(
            global_counts["relevant_retrieved_total"], global_counts["relevant_available_total"]
        ),
        "false_positive_rate": _safe_rate(
            global_counts["false_positive_retrieved_total"], global_counts["retrieved_total"]
        ),
        "average_first_relevant_rank": _safe_rate(
            global_counts["first_relevant_rank_total"], global_counts["first_relevant_rank_count"]
        ),
        "average_exact_top1_gap": _safe_rate(
            sum(float(row["exact_top1_gap"]) for row in asymmetry_rows),
            len(asymmetry_rows),
        ),
        "average_overlap_hit_gap": _safe_rate(
            sum(float(row["overlap_hit_gap"]) for row in asymmetry_rows),
            len(asymmetry_rows),
        ),
    }
    return {
        "summary": summary,
        "matrix": matrix,
        "asymmetry": asymmetry_rows,
    }


def evaluate_thresholds(
    *,
    catalog: AppCatalog,
    records: list[RetrievalRecord],
    thresholds: list[float],
    top_k: int,
    post_filter: PostFilterFn | None = None,
) -> dict[str, object]:
    evaluations: list[dict[str, object]] = []
    for threshold in thresholds:
        result = compute_cross_model_retrieval_matrix(
            catalog=catalog,
            records=records,
            threshold=threshold,
            top_k=top_k,
            post_filter=post_filter,
        )
        summary = dict(cast(dict[str, object], result["summary"]))
        summary["threshold"] = threshold
        summary["balanced_score"] = round(
            (
                cast(float, summary["exact_top1_rate"])
                + cast(float, summary["overlap_hit_rate"])
                + cast(float, summary["overlap_precision_at_k"])
                + cast(float, summary["recall_at_k"])
                - cast(float, summary["false_positive_rate"])
            ),
            4,
        )
        evaluations.append(summary)

    best = max(evaluations, key=lambda evaluation: cast(float, evaluation["balanced_score"])) if evaluations else None
    return {
        "evaluations": evaluations,
        "recommended_threshold": best["threshold"] if best is not None else None,
        "recommendation_basis": "balanced_score = exact_top1_rate + overlap_hit_rate + overlap_precision_at_k + recall_at_k - false_positive_rate",
    }
