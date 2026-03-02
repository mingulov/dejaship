from __future__ import annotations

from collections import Counter

from tests.agent_sim._support.types import (
    AppCatalog,
    ScenarioDefinition,
    SimulationDatabaseSnapshot,
    SimulationReport,
)


def assert_simulation_report(
    report: SimulationReport,
    *,
    scenario_name: str,
    scenario: ScenarioDefinition,
) -> None:
    assert report.scenario_name == scenario_name
    assert report.total_agents == scenario.agent_count
    assert len(report.agent_summaries) == scenario.agent_count
    assert report.total_calls == scenario.total_calls_target
    assert report.tool_lists == scenario.agent_count
    assert report.checks >= scenario.agent_count
    assert report.claims >= max(1, scenario.agent_count // 2)
    assert report.errors == 0
    assert report.fixture_source_counts


def assert_swarm_outcomes_have_terminal_states(report: SimulationReport) -> None:
    terminal_total = sum(report.status_counts.values())
    assert terminal_total >= max(1, report.claims // 2)
    assert terminal_total == report.updates


def assert_db_snapshot_matches_report(
    snapshot: SimulationDatabaseSnapshot,
    report: SimulationReport,
) -> None:
    assert snapshot.total_rows == report.claims
    assert snapshot.status_counts == report.status_counts
    assert snapshot.shipped_with_resolution_url == report.status_counts.get("shipped", 0)
    assert snapshot.abandoned_with_resolution_url == 0
    assert snapshot.in_progress_with_resolution_url == 0


def assert_report_has_overlap_pressure(report: SimulationReport, catalog: AppCatalog) -> None:
    brief_to_group = {
        brief.id: brief.expected_overlap_group
        for brief in catalog.briefs
    }
    claimed_groups = Counter(
        brief_to_group[brief_id]
        for summary in report.agent_summaries
        for brief_id in summary.claimed_brief_ids
    )
    assert claimed_groups
    assert any(count >= 2 for count in claimed_groups.values())


def assert_report_uses_only_stored_fixtures(report: SimulationReport) -> None:
    assert report.fixture_source_counts
    assert report.fixture_source_counts.get("synthetic", 0) == 0
    assert report.fixture_source_counts.get("stored", 0) >= 1
