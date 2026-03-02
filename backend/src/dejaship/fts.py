"""Reciprocal Rank Fusion for hybrid vector + full-text search."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dejaship.models import AgentIntent, IntentStatus


def rrf_score(vector_rank: int, fts_rank: int, *, fts_weight: float, k: int) -> float:
    """Compute Reciprocal Rank Fusion score.

    Fuses vector similarity rank and FTS rank into a single score.
    Higher score = more relevant.

    Args:
        vector_rank: 1-based rank from vector search (1 = most similar)
        fts_rank: 1-based rank from FTS (1 = best text match)
        fts_weight: weight for FTS component (1-fts_weight for vector)
        k: RRF smoothing constant (typically 60)
    """
    vector_score = (1.0 - fts_weight) / (k + vector_rank)
    fts_score = fts_weight / (k + fts_rank)
    return vector_score + fts_score


async def hybrid_search(
    session: AsyncSession,
    *,
    query_vector: list[float],
    query_text: str,
    distance_threshold: float,
    fts_weight: float,
    k: int,
    top_n: int,
) -> list[AgentIntent]:
    """Retrieve claims using hybrid vector + FTS search with RRF fusion.

    Runs both vector search and PostgreSQL FTS, then fuses results by
    Reciprocal Rank Fusion.

    Args:
        session: DB session
        query_vector: embedding vector for the query
        query_text: raw text for FTS (core_mechanic + keywords joined)
        distance_threshold: cosine distance threshold for vector search (= 1 - similarity)
        fts_weight: RRF weight given to FTS results (0-1)
        k: RRF smoothing constant
        top_n: number of results to return
    """
    # Vector search candidates
    distance_expr = AgentIntent.embedding.cosine_distance(query_vector)
    vector_query = (
        select(AgentIntent)
        .where(distance_expr <= distance_threshold)
        .where(AgentIntent.status != IntentStatus.ABANDONED)
        .order_by(distance_expr)
        .limit(top_n * 5)
    )
    vector_result = await session.execute(vector_query)
    vector_candidates = list(vector_result.scalars())

    # FTS candidates using plainto_tsquery
    fts_query = (
        select(AgentIntent)
        .where(AgentIntent.search_tsvector.op("@@")(func.plainto_tsquery("english", query_text)))
        .where(AgentIntent.status != IntentStatus.ABANDONED)
        .order_by(func.ts_rank(AgentIntent.search_tsvector, func.plainto_tsquery("english", query_text)).desc())
        .limit(top_n * 5)
    )
    fts_result = await session.execute(fts_query)
    fts_candidates = list(fts_result.scalars())

    # Build rank maps (id -> rank, 1-based)
    vector_rank_map = {c.id: i + 1 for i, c in enumerate(vector_candidates)}
    fts_rank_map = {c.id: i + 1 for i, c in enumerate(fts_candidates)}

    # Union of all candidate IDs
    all_ids = set(vector_rank_map.keys()) | set(fts_rank_map.keys())

    # Candidates that appear only in one set get a default rank beyond the cutoff
    default_rank = top_n * 5 + 1

    # Build id -> object map
    id_to_claim: dict[object, AgentIntent] = {}
    for c in vector_candidates + fts_candidates:
        id_to_claim[c.id] = c

    # Compute RRF scores for all candidates
    scored: list[tuple[float, AgentIntent]] = []
    for claim_id in all_ids:
        vrank = vector_rank_map.get(claim_id, default_rank)
        frank = fts_rank_map.get(claim_id, default_rank)
        score = rrf_score(vrank, frank, fts_weight=fts_weight, k=k)
        scored.append((score, id_to_claim[claim_id]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_n]]
