from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.routing import Mount
from testcontainers.postgres import PostgresContainer

from dejaship.embeddings import load_model
from dejaship.models import Base
from tests.agent_sim._support.catalog import (
    load_app_catalog,
    load_model_matrix,
    load_scenario_matrix,
)
from tests.agent_sim._support.db_snapshot import fetch_simulation_db_snapshot
from tests.agent_sim._support.fixture_store import load_fixture_index
from tests.agent_sim._support.simulation import build_simulation_plan, run_simulation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an agent-sim scenario and export an analyzable report.")
    parser.add_argument("--scenario", default="local", help="Scenario name from scenario_matrix.yaml")
    parser.add_argument("--seed", type=int, default=17, help="Deterministic seed")
    parser.add_argument("--output-json", default="agent-sim-report.json", help="Path to JSON report output")
    parser.add_argument("--output-md", default="agent-sim-report.md", help="Path to Markdown summary output")
    return parser.parse_args()


def render_markdown_summary(report, snapshot) -> str:
    metrics = report.metrics
    lines = [
        f"# Agent Sim Report: {report.scenario_name}",
        "",
        "## Headline",
        f"- Agents: {report.total_agents}",
        f"- Total MCP calls: {report.total_calls}",
        f"- Claims created: {report.claims}",
        f"- Shipped: {report.status_counts.get('shipped', 0)}",
        f"- Abandoned: {report.status_counts.get('abandoned', 0)}",
        f"- Stale cleanup actions: {report.stale_cleanup_actions}",
        f"- Unique claimed briefs: {len(report.unique_claimed_briefs)}",
        "",
        "## Quality Metrics",
        f"- Claim rate per agent: {metrics.claim_rate}",
        f"- Ship rate: {metrics.ship_rate}",
        f"- Abandon rate: {metrics.abandon_rate}",
        f"- Stale cleanup rate: {metrics.stale_cleanup_rate}",
        f"- Crowded check rate: {metrics.crowded_check_rate}",
        f"- Stored fixture ratio: {metrics.stored_fixture_ratio}",
        f"- Duplicate brief claim rate: {metrics.duplicate_brief_claim_rate}",
        f"- Unresolved claim rate: {metrics.unresolved_claim_rate}",
        f"- Avg in-progress density: {metrics.average_density_in_progress}",
        f"- Avg shipped density: {metrics.average_density_shipped}",
        f"- Avg abandoned density: {metrics.average_density_abandoned}",
        f"- Overlap hit rate: {metrics.overlap_hit_rate}",
        f"- Overlap precision: {metrics.overlap_precision}",
        f"- Overlap recall proxy: {metrics.overlap_recall_proxy}",
        f"- Claim when clear rate: {metrics.claim_when_clear_rate}",
        f"- Skip when crowded rate: {metrics.skip_when_crowded_rate}",
        f"- Revision success rate: {metrics.revision_success_rate}",
        f"- Duplicate overlap-group claim rate: {metrics.duplicate_overlap_group_rate}",
        "",
        "## Quality Flags",
    ]
    if metrics.quality_flags:
        lines.extend(f"- {flag}" for flag in metrics.quality_flags)
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Per Model",
        ]
    )
    for model_alias, summary in sorted(report.model_summaries.items()):
        lines.append(
            f"- {model_alias}: claims={summary.claims}, shipped={summary.shipped}, "
            f"abandoned={summary.abandoned}, stale_abandoned={summary.stale_abandoned}, "
            f"crowded_checks={summary.crowded_checks}, overlap_hits={summary.overlap_hits}/{summary.overlap_evaluable_checks}, "
            f"overlap_precision={summary.overlap_precision}, overlap_recall_proxy={summary.overlap_recall_proxy}, "
            f"unique_briefs={len(summary.unique_claimed_briefs)}"
        )

    lines.extend(
        [
            "",
            "## Per Persona",
        ]
    )
    for persona, summary in sorted(report.persona_summaries.items()):
        lines.append(
            f"- {persona}: agents={summary.total_agents}, claims={summary.claims}, skips={summary.skips}, "
            f"claim_when_clear_rate={round(summary.claims_after_clear / summary.clear_decisions, 4) if summary.clear_decisions else 0.0}, "
            f"skip_when_crowded_rate={round(summary.skips_after_crowded / summary.crowded_decisions, 4) if summary.crowded_decisions else 0.0}, "
            f"revision_success_rate={round(summary.revision_successes / summary.revision_attempts, 4) if summary.revision_attempts else 0.0}"
        )

    lines.extend(
        [
            "",
            "## Database Snapshot",
            f"- Persisted rows: {snapshot.total_rows}",
            f"- Status counts: {json.dumps(snapshot.status_counts, sort_keys=True)}",
        ]
    )
    return "\n".join(lines) + "\n"


@contextlib.asynccontextmanager
async def build_mcp_http_client(engine):
    from dejaship.mcp import server as mcp_server

    mcp_server.mcp._session_manager = None
    mcp_app = mcp_server.mcp.streamable_http_app()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    original_async_session = mcp_server.async_session
    original_transport_security = mcp_server.mcp.settings.transport_security.model_copy(deep=True)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        load_model()
        async with mcp_server.mcp.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.router.routes.append(Mount("/mcp", app=mcp_app))

    mcp_server.async_session = session_factory
    mcp_server.mcp.settings.transport_security.enable_dns_rebinding_protection = True
    mcp_server.mcp.settings.transport_security.allowed_hosts = [
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
    ]
    mcp_server.mcp.settings.transport_security.allowed_origins = [
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:*",
        "http://127.0.0.1:*",
    ]

    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://localhost",
                follow_redirects=True,
            ) as client:
                yield client
    finally:
        mcp_server.async_session = original_async_session
        mcp_server.mcp.settings.transport_security = original_transport_security


async def main() -> None:
    args = parse_args()
    app_catalog = load_app_catalog()
    model_matrix = load_model_matrix()
    scenario_matrix = load_scenario_matrix(model_matrix)
    fixture_index = load_fixture_index()
    scenario = scenario_matrix.scenarios[args.scenario]
    plan = build_simulation_plan(
        scenario_name=args.scenario,
        scenario=scenario,
        model_matrix=model_matrix,
        catalog=app_catalog,
        seed=args.seed,
    )

    with PostgresContainer(
        image="pgvector/pgvector:pg17",
        username="test",
        password="test",
        dbname="test",
    ) as container:
        url = container.get_connection_url().replace("psycopg2", "asyncpg")
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)

        try:
            async with build_mcp_http_client(engine) as http_client:
                report = await run_simulation(
                    plan=plan,
                    catalog=app_catalog,
                    fixture_index=fixture_index,
                    http_client=http_client,
                    base_url="http://localhost/mcp/",
                    engine=engine,
                )
            snapshot = await fetch_simulation_db_snapshot(engine)
        finally:
            await engine.dispose()

    json_path = Path(args.output_json)
    md_path = Path(args.output_md)
    json_path.write_text(
        json.dumps(
            {
                "report": report.model_dump(mode="json"),
                "db_snapshot": snapshot.model_dump(mode="json"),
            },
            indent=2,
        )
    )
    md_path.write_text(render_markdown_summary(report, snapshot))
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
