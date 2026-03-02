import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from dejaship.config import settings

KEYWORD_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")


class IntentInput(BaseModel):
    """Input for checking or claiming a project intent."""

    core_mechanic: str = Field(
        ...,
        min_length=1,
        max_length=settings.CORE_MECHANIC_MAX_LENGTH,
        description="A short description of the core product mechanic you plan to build.",
        examples=["AI-powered HVAC maintenance scheduling with predictive failure detection"],
    )
    keywords: list[str] = Field(
        ...,
        min_length=settings.MIN_KEYWORDS,
        max_length=settings.MAX_KEYWORDS,
        description="5-50 lowercase keywords describing the project. Each 3-40 chars, alphanumeric with hyphens.",
        examples=[["hvac", "maintenance", "scheduling", "predictive", "field-service"]],
    )

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: list[str]) -> list[str]:
        for kw in v:
            if len(kw) < settings.KEYWORD_MIN_LENGTH or len(kw) > settings.KEYWORD_MAX_LENGTH:
                raise ValueError(
                    f"Each keyword must be {settings.KEYWORD_MIN_LENGTH}-{settings.KEYWORD_MAX_LENGTH} chars, got '{kw}'"
                )
            if not KEYWORD_PATTERN.match(kw):
                raise ValueError(
                    f"Keywords must be lowercase alphanumeric with hyphens, got '{kw}'"
                )
        return v


class NeighborhoodDensity(BaseModel):
    """Counts of claims in the semantic neighborhood, grouped by status."""

    in_progress: int = Field(description="Claims currently being built", examples=[3])
    shipped: int = Field(description="Claims that have been shipped", examples=[12])
    abandoned: int = Field(description="Claims that were abandoned", examples=[5])


class ActiveClaim(BaseModel):
    """A claim in the semantic neighborhood that is currently active."""

    mechanic: str = Field(description="The core mechanic description of this claim", examples=["AI-powered HVAC maintenance scheduling with predictive failure detection"])
    status: str = Field(description="Current status: in_progress or shipped", examples=["in_progress"])
    age_hours: float = Field(description="Hours since this claim was created", examples=[4.5])


class CheckResponse(BaseModel):
    """Result of checking the semantic airspace for a project idea."""

    neighborhood_density: NeighborhoodDensity = Field(description="Counts by status in the neighborhood")
    closest_active_claims: list[ActiveClaim] = Field(description="The closest non-abandoned claims, ordered by similarity")


class ClaimResponse(BaseModel):
    """Result of claiming an intent to build a project."""

    claim_id: UUID = Field(description="Unique identifier for this claim", examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    edit_token: str = Field(description="Secret token for updating this claim. Store it safely — it cannot be recovered.", examples=["abc123def456"])
    status: str = Field(description="Initial status (always 'in_progress')", examples=["in_progress"])
    timestamp: datetime = Field(description="When the claim was created", examples=["2026-03-02T10:00:00Z"])


class UpdateInput(BaseModel):
    """Input for updating an existing claim's status."""

    claim_id: UUID = Field(description="The claim_id returned from /v1/claim", examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    edit_token: str = Field(..., max_length=256, description="The secret edit_token returned from /v1/claim", examples=["abc123def456"])
    status: str = Field(..., pattern=r"^(shipped|abandoned)$", description="New status: 'shipped' or 'abandoned'", examples=["shipped"])
    resolution_url: str | None = Field(default=None, max_length=2048, description="The live URL if status is 'shipped' (optional)", examples=["https://myapp.com"])


class UpdateResponse(BaseModel):
    """Result of updating a claim."""

    success: bool = Field(description="Whether the update succeeded", examples=[True])


class StatsResponse(BaseModel):
    """Public statistics about the global intent ledger."""

    total_claims: int = Field(description="Total claims ever created", examples=[150])
    active: int = Field(description="Claims currently in_progress", examples=[42])
    shipped: int = Field(description="Claims that shipped", examples=[85])
    abandoned: int = Field(description="Claims that were abandoned", examples=[23])
