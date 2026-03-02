import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from starlette.concurrency import run_in_threadpool

from dejaship.config import settings
from dejaship.embeddings import build_embedding_text, cosine_similarity, embed_text
from dejaship.filters import apply_jaccard_filter
from dejaship.models import AgentIntent, IntentStatus
from dejaship.schemas import (
    ActiveClaim,
    CheckResponse,
    ClaimResponse,
    IntentInput,
    NeighborhoodDensity,
    UpdateInput,
    UpdateResponse,
)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _check_airspace_two_stage(
    input: IntentInput,
    session: AsyncSession,
    *,
    combined_vector: list[float],
    stage1_threshold: float,
    stage2_threshold: float,
    candidate_multiplier: int,
    top_k: int,
) -> list[AgentIntent]:
    """Stage 1: broad retrieval; Stage 2: rerank by mechanic embedding.

    Candidates without mechanic_embedding (pre-migration rows) are included
    with a neutral score so they are not silently dropped.
    """
    mechanic_vector = await run_in_threadpool(embed_text, input.core_mechanic)

    distance_expr = AgentIntent.embedding.cosine_distance(combined_vector)
    distance_threshold = 1.0 - stage1_threshold

    candidates_query = (
        select(AgentIntent)
        .where(distance_expr <= distance_threshold)
        .where(AgentIntent.status != IntentStatus.ABANDONED)
        .order_by(distance_expr)
        .limit(top_k * candidate_multiplier)
    )
    result = await session.execute(candidates_query)
    candidates = list(result.scalars())

    # Stage 2: rerank by mechanic similarity, filter at stage2_threshold.
    # Claims with no mechanic_embedding (pre-migration) pass through with score 0.0
    # so they are not silently dropped during rollout.
    scored = []
    for claim in candidates:
        if claim.mechanic_embedding is None:
            scored.append((0.0, claim))
            continue
        sim = cosine_similarity(mechanic_vector, list(claim.mechanic_embedding))
        if sim >= stage2_threshold:
            scored.append((sim, claim))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [claim for _, claim in scored[:top_k]]


async def check_airspace(input: IntentInput, session: AsyncSession) -> CheckResponse:
    text = build_embedding_text(input.core_mechanic, input.keywords)
    vector = await run_in_threadpool(embed_text, text)

    # cosine_distance = 1 - cosine_similarity, so threshold becomes 1 - similarity
    distance_threshold = 1.0 - settings.SIMILARITY_THRESHOLD

    distance_expr = AgentIntent.embedding.cosine_distance(vector)

    # density counts ALL vector-nearby records by status (raw vector neighbourhood signal).
    # closest_active_claims is a curated list that may be further narrowed by post-filters
    # (e.g. Jaccard). The two intentionally differ: density tells you "how crowded is this
    # space?", closest tells you "which specific claims should you be aware of?".
    # Count by status
    count_query = (
        select(
            AgentIntent.status,
            func.count().label("cnt"),
        )
        .where(distance_expr <= distance_threshold)
        .group_by(AgentIntent.status)
    )
    result = await session.execute(count_query)
    counts = {row.status: row.cnt for row in result}

    density = NeighborhoodDensity(
        in_progress=counts.get(IntentStatus.IN_PROGRESS, 0),
        shipped=counts.get(IntentStatus.SHIPPED, 0),
        abandoned=counts.get(IntentStatus.ABANDONED, 0),
    )

    # Get closest active claims
    now = datetime.now(timezone.utc)
    if settings.ENABLE_TWO_STAGE_RETRIEVAL:
        intents = await _check_airspace_two_stage(
            input, session,
            combined_vector=vector,
            stage1_threshold=settings.STAGE1_THRESHOLD,
            stage2_threshold=settings.STAGE2_THRESHOLD,
            candidate_multiplier=settings.STAGE2_CANDIDATE_MULTIPLIER,
            top_k=settings.MAX_CLOSEST_RESULTS,
        )
    else:
        closest_query = (
            select(AgentIntent)
            .where(distance_expr <= distance_threshold)
            .where(AgentIntent.status != IntentStatus.ABANDONED)
            .order_by(distance_expr)
            .limit(settings.MAX_CLOSEST_RESULTS)
        )
        result = await session.execute(closest_query)
        intents = list(result.scalars())
        if settings.ENABLE_JACCARD_FILTER:
            intents = apply_jaccard_filter(
                query_keywords=input.keywords,
                candidates=intents,
                threshold=settings.JACCARD_THRESHOLD,
                min_keywords=settings.JACCARD_MIN_KEYWORDS,
            )
    closest = []
    for intent in intents:
        age_hours = (now - intent.created_at.astimezone(timezone.utc)).total_seconds() / 3600
        closest.append(
            ActiveClaim(
                mechanic=intent.core_mechanic,
                status=intent.status.value,
                age_hours=round(age_hours, 1),
            )
        )

    return CheckResponse(neighborhood_density=density, closest_active_claims=closest)


async def claim_intent(input: IntentInput, session: AsyncSession) -> ClaimResponse:
    text = build_embedding_text(input.core_mechanic, input.keywords)
    vector = await run_in_threadpool(embed_text, text)
    mechanic_vector = await run_in_threadpool(embed_text, input.core_mechanic)  # NEW

    edit_token = secrets.token_urlsafe(32)

    intent = AgentIntent(
        core_mechanic=input.core_mechanic,
        keywords=input.keywords,
        embedding=vector,
        mechanic_embedding=mechanic_vector,  # NEW
        edit_token_hash=_hash_token(edit_token),
    )
    session.add(intent)
    await session.commit()
    await session.refresh(intent)

    return ClaimResponse(
        claim_id=intent.id,
        edit_token=edit_token,
        status=intent.status.value,
        timestamp=intent.created_at,
    )


async def update_claim(input: UpdateInput, session: AsyncSession) -> UpdateResponse:
    intent = await session.get(AgentIntent, input.claim_id)
    if intent is None:
        raise ValueError("Claim not found")

    # Constant-time token comparison
    if not hmac.compare_digest(_hash_token(input.edit_token), intent.edit_token_hash):
        raise PermissionError("Invalid edit token")

    # Validate state transition
    if intent.status != IntentStatus.IN_PROGRESS:
        raise ValueError(f"Cannot transition from {intent.status.value}")

    intent.status = IntentStatus(input.status)
    intent.resolution_url = input.resolution_url
    intent.updated_at = datetime.now(timezone.utc)
    await session.commit()

    return UpdateResponse(success=True)
