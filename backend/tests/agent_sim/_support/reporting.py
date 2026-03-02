from __future__ import annotations

from collections import Counter

from tests.agent_sim._support.types import (
    AppCatalog,
    AgentRunSummary,
    ModelSimulationSummary,
    PersonaSimulationSummary,
    SimulationMetrics,
    SimulationReport,
)


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _build_quality_flags(
    *,
    claim_rate: float,
    ship_rate: float,
    abandon_rate: float,
    stale_cleanup_rate: float,
    crowded_check_rate: float,
    stored_fixture_ratio: float,
    duplicate_brief_claim_rate: float,
    unresolved_claim_rate: float,
    overlap_hit_rate: float,
    overlap_precision: float,
    overlap_recall_proxy: float,
    claim_when_clear_rate: float,
    skip_when_crowded_rate: float,
    revision_success_rate: float,
    duplicate_overlap_group_rate: float,
    partial_keyword_request_rate: float,
) -> list[str]:
    flags: list[str] = []
    if ship_rate < 0.45:
        flags.append("low-ship-rate")
    if abandon_rate > 0.35:
        flags.append("high-abandon-rate")
    if stale_cleanup_rate > 0.15:
        flags.append("high-stale-cleanup-rate")
    if stored_fixture_ratio < 0.95:
        flags.append("synthetic-fallback-present")
    if duplicate_brief_claim_rate > 0.2:
        flags.append("high-duplicate-claim-rate")
    if unresolved_claim_rate > 0.05:
        flags.append("open-claims-remain")
    if crowded_check_rate < 0.1:
        flags.append("low-overlap-detection-signal")
    if overlap_hit_rate < 0.5:
        flags.append("low-overlap-hit-rate")
    if overlap_precision < 0.35:
        flags.append("low-overlap-precision")
    if overlap_recall_proxy < 0.35:
        flags.append("low-overlap-recall-proxy")
    if claim_when_clear_rate < 0.6:
        flags.append("hesitant-on-clear-airspace")
    if skip_when_crowded_rate < 0.35:
        flags.append("weak-crowded-skip-discipline")
    if revision_success_rate < 0.25:
        flags.append("weak-revision-recovery")
    if duplicate_overlap_group_rate > 0.45:
        flags.append("high-same-group-collision-rate")
    if partial_keyword_request_rate > 0.0 and overlap_hit_rate < 0.4:
        flags.append("partial-keyword-search-fragile")
    if claim_rate < 0.4:
        flags.append("low-claim-rate")
    return flags


def _related_brief_ids(catalog: AppCatalog, brief_id: str) -> set[str]:
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


def _compute_overlap_metrics(
    *,
    catalog: AppCatalog,
    summaries: list[AgentRunSummary],
    model_summaries: dict[str, ModelSimulationSummary],
) -> tuple[float, float, float]:
    claim_events = [
        event
        for summary in summaries
        for event in summary.events
        if event.event_type == "claim" and event.brief_id and event.core_mechanic
    ]
    all_claimed_briefs = {event.brief_id for event in claim_events}
    mechanic_to_brief_ids: dict[str, set[str]] = {}
    for event in claim_events:
        mechanic_to_brief_ids.setdefault(event.core_mechanic, set()).add(event.brief_id)

    evaluable_checks = 0
    hit_count = 0
    precision_numerator = 0
    precision_denominator = 0
    recall_numerator = 0
    recall_denominator = 0

    model_totals: dict[str, dict[str, int]] = {}

    check_events = [
        event
        for summary in summaries
        for event in summary.events
        if event.event_type == "check" and event.brief_id
    ]
    for event in check_events:
        related_briefs = _related_brief_ids(catalog, event.brief_id) & all_claimed_briefs
        if not related_briefs:
            continue

        retrieved_briefs = {
            brief_id
            for mechanic in event.closest_mechanics
            for brief_id in mechanic_to_brief_ids.get(mechanic, set())
            if brief_id != event.brief_id
        }
        relevant_hits = retrieved_briefs & related_briefs
        model_total = model_totals.setdefault(
            event.model_alias,
            {"evaluable": 0, "hits": 0, "precision_num": 0, "precision_den": 0, "recall_num": 0, "recall_den": 0},
        )

        evaluable_checks += 1
        model_total["evaluable"] += 1
        if relevant_hits:
            hit_count += 1
            model_total["hits"] += 1

        precision_numerator += len(relevant_hits)
        precision_denominator += len(retrieved_briefs)
        recall_numerator += len(relevant_hits)
        recall_denominator += len(related_briefs)

        model_total["precision_num"] += len(relevant_hits)
        model_total["precision_den"] += len(retrieved_briefs)
        model_total["recall_num"] += len(relevant_hits)
        model_total["recall_den"] += len(related_briefs)

    for model_alias, totals in model_totals.items():
        model_summary = model_summaries[model_alias]
        model_summary.overlap_evaluable_checks = totals["evaluable"]
        model_summary.overlap_hits = totals["hits"]
        model_summary.overlap_precision = _safe_rate(totals["precision_num"], totals["precision_den"])
        model_summary.overlap_recall_proxy = _safe_rate(totals["recall_num"], totals["recall_den"])

    return (
        _safe_rate(hit_count, evaluable_checks),
        _safe_rate(precision_numerator, precision_denominator),
        _safe_rate(recall_numerator, recall_denominator),
    )


def _compute_decision_metrics(
    *,
    catalog: AppCatalog,
    summaries: list[AgentRunSummary],
) -> tuple[dict[str, PersonaSimulationSummary], dict[str, float]]:
    brief_to_group = {brief.id: brief.expected_overlap_group for brief in catalog.briefs}
    group_claim_counts = Counter(
        brief_to_group[brief_id]
        for summary in summaries
        for brief_id in summary.claimed_brief_ids
    )
    duplicate_overlap_claims = sum(max(0, count - 1) for count in group_claim_counts.values())

    persona_summaries: dict[str, PersonaSimulationSummary] = {}
    clear_decisions = 0
    claims_after_clear = 0
    crowded_decisions = 0
    skips_after_crowded = 0
    revision_attempts = 0
    revision_successes = 0

    for summary in summaries:
        persona_summary = persona_summaries.setdefault(
            summary.persona,
            PersonaSimulationSummary(persona=summary.persona),
        )
        persona_summary.total_agents += 1
        persona_summary.claims += summary.claims
        persona_summary.skips += summary.skips
        persona_summary.partial_keyword_requests += summary.partial_keyword_requests

        last_check_by_brief: dict[str, object] = {}
        saw_crowded_other_brief = False
        for event in summary.events:
            if event.event_type == "check" and event.brief_id:
                last_check_by_brief[event.brief_id] = event
                if event.crowded:
                    saw_crowded_other_brief = True
                continue

            if event.event_type not in {"claim", "skip"} or not event.brief_id:
                continue

            prior_check = last_check_by_brief.get(event.brief_id)
            if prior_check is not None:
                if prior_check.crowded:
                    crowded_decisions += 1
                    persona_summary.crowded_decisions += 1
                    if event.event_type == "skip":
                        skips_after_crowded += 1
                        persona_summary.skips_after_crowded += 1
                else:
                    clear_decisions += 1
                    persona_summary.clear_decisions += 1
                    if event.event_type == "claim":
                        claims_after_clear += 1
                        persona_summary.claims_after_clear += 1

            if event.event_type == "claim":
                other_checked_briefs = {
                    check_event.brief_id
                    for check_event in summary.events
                    if check_event.event_type == "check" and check_event.brief_id and check_event.brief_id != event.brief_id
                }
                if saw_crowded_other_brief and other_checked_briefs:
                    revision_attempts += 1
                    persona_summary.revision_attempts += 1
                    revision_successes += 1
                    persona_summary.revision_successes += 1

    return persona_summaries, {
        "claim_when_clear_rate": _safe_rate(claims_after_clear, clear_decisions),
        "skip_when_crowded_rate": _safe_rate(skips_after_crowded, crowded_decisions),
        "revision_success_rate": _safe_rate(revision_successes, revision_attempts),
        "duplicate_overlap_group_rate": _safe_rate(
            duplicate_overlap_claims,
            sum(summary.claims for summary in summaries),
        ),
    }


def build_simulation_report(
    *,
    scenario_name: str,
    summaries: list[AgentRunSummary],
    catalog: AppCatalog,
) -> SimulationReport:
    status_counts = Counter(
        status
        for summary in summaries
        for status in summary.completed_statuses
    )
    fixture_source_counts = Counter(
        source
        for summary in summaries
        for source in summary.fixture_sources
    )
    unresolved_claim_ids = sorted(
        {
            claim_id
            for summary in summaries
            for claim_id in summary.unresolved_claim_ids
        }
    )
    unique_claimed_briefs = sorted(
        {
            brief_id
            for summary in summaries
            for brief_id in summary.claimed_brief_ids
        }
    )
    duplicate_claim_count = sum(summary.claims for summary in summaries) - len(unique_claimed_briefs)
    density_events = [
        event
        for summary in summaries
        for event in summary.events
        if event.event_type == "check"
    ]
    model_summaries: dict[str, ModelSimulationSummary] = {}
    for summary in summaries:
        model_summary = model_summaries.setdefault(
            summary.model_alias,
            ModelSimulationSummary(model_alias=summary.model_alias),
        )
        model_summary.total_agents += 1
        model_summary.checks += summary.checks
        model_summary.claims += summary.claims
        model_summary.updates += summary.updates
        model_summary.shipped += len(summary.shipped_claim_ids)
        model_summary.abandoned += len(summary.abandoned_claim_ids)
        model_summary.stale_abandoned += len(summary.stale_abandoned_claim_ids)
        model_summary.skips += summary.skips
        model_summary.errors += summary.errors
        model_summary.crowded_checks += summary.crowded_checks
        model_summary.partial_keyword_requests += summary.partial_keyword_requests
        model_summary.unique_claimed_briefs = sorted(
            set(model_summary.unique_claimed_briefs) | set(summary.claimed_brief_ids)
        )

    overlap_hit_rate, overlap_precision, overlap_recall_proxy = _compute_overlap_metrics(
        catalog=catalog,
        summaries=summaries,
        model_summaries=model_summaries,
    )
    persona_summaries, decision_metrics = _compute_decision_metrics(
        catalog=catalog,
        summaries=summaries,
    )

    total_claims = sum(summary.claims for summary in summaries)
    shipped_total = sum(len(summary.shipped_claim_ids) for summary in summaries)
    abandoned_total = sum(len(summary.abandoned_claim_ids) for summary in summaries)
    stale_abandoned_total = sum(len(summary.stale_abandoned_claim_ids) for summary in summaries)
    total_stored = fixture_source_counts.get("stored", 0)
    total_fixture_source_events = sum(fixture_source_counts.values())
    metrics = SimulationMetrics(
        claim_rate=_safe_rate(total_claims, len(summaries)),
        ship_rate=_safe_rate(shipped_total, total_claims),
        abandon_rate=_safe_rate(abandoned_total, total_claims),
        stale_cleanup_rate=_safe_rate(stale_abandoned_total, total_claims),
        crowded_check_rate=_safe_rate(
            sum(summary.crowded_checks for summary in summaries),
            sum(summary.checks for summary in summaries),
        ),
        stored_fixture_ratio=_safe_rate(total_stored, total_fixture_source_events),
        duplicate_brief_claim_rate=_safe_rate(duplicate_claim_count, total_claims),
        unresolved_claim_rate=_safe_rate(len(unresolved_claim_ids), total_claims),
        partial_keyword_request_rate=_safe_rate(
            sum(summary.partial_keyword_requests for summary in summaries),
            sum(summary.checks for summary in summaries),
        ),
        average_density_in_progress=round(
            sum(event.density_in_progress or 0 for event in density_events) / max(1, len(density_events)),
            4,
        ),
        average_density_shipped=round(
            sum(event.density_shipped or 0 for event in density_events) / max(1, len(density_events)),
            4,
        ),
        average_density_abandoned=round(
            sum(event.density_abandoned or 0 for event in density_events) / max(1, len(density_events)),
            4,
        ),
        overlap_hit_rate=overlap_hit_rate,
        overlap_precision=overlap_precision,
        overlap_recall_proxy=overlap_recall_proxy,
        claim_when_clear_rate=decision_metrics["claim_when_clear_rate"],
        skip_when_crowded_rate=decision_metrics["skip_when_crowded_rate"],
        revision_success_rate=decision_metrics["revision_success_rate"],
        duplicate_overlap_group_rate=decision_metrics["duplicate_overlap_group_rate"],
    )
    metrics.quality_flags = _build_quality_flags(
        claim_rate=metrics.claim_rate,
        ship_rate=metrics.ship_rate,
        abandon_rate=metrics.abandon_rate,
        stale_cleanup_rate=metrics.stale_cleanup_rate,
        crowded_check_rate=metrics.crowded_check_rate,
        stored_fixture_ratio=metrics.stored_fixture_ratio,
        duplicate_brief_claim_rate=metrics.duplicate_brief_claim_rate,
        unresolved_claim_rate=metrics.unresolved_claim_rate,
        overlap_hit_rate=metrics.overlap_hit_rate,
        overlap_precision=metrics.overlap_precision,
        overlap_recall_proxy=metrics.overlap_recall_proxy,
        claim_when_clear_rate=metrics.claim_when_clear_rate,
        skip_when_crowded_rate=metrics.skip_when_crowded_rate,
        revision_success_rate=metrics.revision_success_rate,
        duplicate_overlap_group_rate=metrics.duplicate_overlap_group_rate,
        partial_keyword_request_rate=metrics.partial_keyword_request_rate,
    )
    return SimulationReport(
        scenario_name=scenario_name,
        total_agents=len(summaries),
        total_calls=sum(
            summary.tool_lists + summary.checks + summary.claims + summary.updates
            for summary in summaries
        ),
        tool_lists=sum(summary.tool_lists for summary in summaries),
        checks=sum(summary.checks for summary in summaries),
        claims=sum(summary.claims for summary in summaries),
        updates=sum(summary.updates for summary in summaries),
        stale_cleanup_actions=sum(summary.stale_cleanup_actions for summary in summaries),
        errors=sum(summary.errors for summary in summaries),
        skips=sum(summary.skips for summary in summaries),
        status_counts=dict(status_counts),
        fixture_source_counts=dict(fixture_source_counts),
        unique_claimed_briefs=unique_claimed_briefs,
        unresolved_claim_ids=unresolved_claim_ids,
        event_count=sum(len(summary.events) for summary in summaries),
        model_summaries=model_summaries,
        persona_summaries=persona_summaries,
        metrics=metrics,
        agent_summaries=summaries,
    )
