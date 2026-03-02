from __future__ import annotations

from collections import Counter

from tests.agent_sim._support.types import AgentRunSummary, SimulationReport


def build_simulation_report(
    *,
    scenario_name: str,
    summaries: list[AgentRunSummary],
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
    unique_claimed_briefs = sorted(
        {
            brief_id
            for summary in summaries
            for brief_id in summary.claimed_brief_ids
        }
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
        errors=sum(summary.errors for summary in summaries),
        skips=sum(summary.skips for summary in summaries),
        status_counts=dict(status_counts),
        fixture_source_counts=dict(fixture_source_counts),
        unique_claimed_briefs=unique_claimed_briefs,
        agent_summaries=summaries,
    )
