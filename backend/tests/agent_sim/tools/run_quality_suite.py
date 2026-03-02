from __future__ import annotations

import argparse
import contextlib
import json
from collections import Counter
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.routing import Mount
from testcontainers.postgres import PostgresContainer

from dejaship.config import settings
from dejaship.embeddings import embed_text, load_model
from dejaship.models import Base
from tests.agent_sim._support.catalog import (
    load_app_catalog,
    load_model_matrix,
    load_scenario_matrix,
    resolve_enabled_model_aliases,
    resolve_model_set,
)
from tests.agent_sim._support.db_snapshot import fetch_simulation_db_snapshot
from tests.agent_sim._support.embedding_variants import build_variant_text, supported_embedding_variants
from tests.agent_sim._support.fixture_store import iter_fixture_paths, load_fixture_index, read_fixture
from tests.agent_sim._support.retrieval_analysis import (
    RetrievalRecord,
    compute_cross_model_retrieval_matrix,
    evaluate_thresholds,
)
from tests.agent_sim._support.simulation import build_simulation_plan, run_simulation
from tests.agent_sim.tools.run_agent_sim_report import render_markdown_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full DejaShip agent-sim quality bundle.")
    parser.add_argument("--scenario", default="smoke")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--model-set", default="default")
    parser.add_argument("--model-alias", action="append", default=[])
    parser.add_argument("--threshold-start", type=float, default=0.55)
    parser.add_argument("--threshold-stop", type=float, default=0.9)
    parser.add_argument("--threshold-step", type=float, default=0.05)
    parser.add_argument("--output-dir", default="agent-sim-quality-bundle")
    return parser.parse_args()


def _float_range(start: float, stop: float, step: float) -> list[float]:
    values: list[float] = []
    current = start
    while current <= stop + 1e-9:
        values.append(round(current, 4))
        current += step
    return values


def _fixture_coverage_snapshot() -> dict[str, object]:
    catalog = load_app_catalog()
    model_matrix = load_model_matrix()
    fixture_paths = iter_fixture_paths()
    fixture_count_by_model: Counter[str] = Counter()
    brief_count_by_model: dict[str, set[str]] = {}

    for path in fixture_paths:
        fixture = read_fixture(path)
        fixture_count_by_model[fixture.metadata.model_alias] += 1
        brief_count_by_model.setdefault(fixture.metadata.model_alias, set()).add(fixture.brief_id)

    enabled_models = [alias for alias, entry in model_matrix.models.items() if entry.enabled]
    total_briefs = len(catalog.briefs)
    return {
        "stored_fixtures": len(fixture_paths),
        "catalog_briefs": total_briefs,
        "enabled_models": len(enabled_models),
        "coverage_by_model": {
            model_alias: {
                "brief_count": len(brief_count_by_model.get(model_alias, set())),
                "fixture_count": fixture_count_by_model.get(model_alias, 0),
            }
            for model_alias in sorted(enabled_models)
        },
    }


def _build_records(app_catalog, selected_models, fixture_index) -> list[RetrievalRecord]:
    records: list[RetrievalRecord] = []
    for model_alias, _ in selected_models:
        for brief in app_catalog.briefs:
            fixture = fixture_index.get(brief_id=brief.id, model_alias=model_alias)
            if fixture is None:
                continue
            text = build_variant_text(
                variant="current_combined",
                core_mechanic=fixture.final_intent_input.core_mechanic,
                keywords=fixture.final_intent_input.keywords,
                brief=brief,
                keyword_repeat=settings.KEYWORD_REPEAT,
            )
            records.append(
                RetrievalRecord(
                    brief_id=brief.id,
                    model_alias=model_alias,
                    vector=embed_text(text),
                )
            )
    return records


def _build_ablation_rows(app_catalog, selected_models, fixture_index, threshold: float, top_k: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    brief_map = {brief.id: brief for brief in app_catalog.briefs}
    for variant in supported_embedding_variants():
        repeats = [1, settings.KEYWORD_REPEAT, 3, 4] if variant == "current_combined" else [settings.KEYWORD_REPEAT]
        for keyword_repeat in repeats:
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
                threshold=threshold,
                top_k=top_k,
            )
            summary = dict(result["summary"])
            summary["variant"] = variant
            summary["keyword_repeat"] = keyword_repeat
            rows.append(summary)
    return rows


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
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    app_catalog = load_app_catalog()
    model_matrix = load_model_matrix()
    scenario_matrix = load_scenario_matrix(model_matrix)
    fixture_index = load_fixture_index()
    selected_models = (
        resolve_enabled_model_aliases(model_matrix, args.model_alias)
        if args.model_alias
        else resolve_model_set(model_matrix, args.model_set)
    )

    load_model()
    retrieval_records = _build_records(app_catalog, selected_models, fixture_index)
    cross_model = compute_cross_model_retrieval_matrix(
        catalog=app_catalog,
        records=retrieval_records,
        threshold=settings.SIMILARITY_THRESHOLD,
        top_k=settings.MAX_CLOSEST_RESULTS,
    )
    threshold_sweep = evaluate_thresholds(
        catalog=app_catalog,
        records=retrieval_records,
        thresholds=_float_range(args.threshold_start, args.threshold_stop, args.threshold_step),
        top_k=settings.MAX_CLOSEST_RESULTS,
    )
    ablation = {
        "threshold": settings.SIMILARITY_THRESHOLD,
        "top_k": settings.MAX_CLOSEST_RESULTS,
        "variants": _build_ablation_rows(
            app_catalog,
            selected_models,
            fixture_index,
            threshold=settings.SIMILARITY_THRESHOLD,
            top_k=settings.MAX_CLOSEST_RESULTS,
        ),
    }

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

    manifest = {
        "git_sha": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "scenario": args.scenario,
        "seed": args.seed,
        "embedding_model": settings.EMBEDDING_MODEL,
        "similarity_threshold": settings.SIMILARITY_THRESHOLD,
        "keyword_repeat": settings.KEYWORD_REPEAT,
        "model_selection": [alias for alias, _ in selected_models],
        "fixture_coverage": _fixture_coverage_snapshot(),
    }

    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (output_dir / "swarm_report.json").write_text(
        json.dumps(
            {"report": report.model_dump(mode="json"), "db_snapshot": snapshot.model_dump(mode="json")},
            indent=2,
        )
    )
    (output_dir / "swarm_report.md").write_text(render_markdown_summary(report, snapshot))
    (output_dir / "cross_model_retrieval.json").write_text(json.dumps(cross_model, indent=2))
    (output_dir / "threshold_sweep.json").write_text(json.dumps(threshold_sweep, indent=2))
    (output_dir / "embedding_ablation.json").write_text(json.dumps(ablation, indent=2))
    print(f"wrote {output_dir}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
