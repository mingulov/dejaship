import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from dejaship.config import settings

KEYWORD_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]{1,2}$")


class IntentInput(BaseModel):
    core_mechanic: str = Field(..., min_length=1, max_length=settings.CORE_MECHANIC_MAX_LENGTH)
    keywords: list[str] = Field(..., min_length=settings.MIN_KEYWORDS)

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
    in_progress: int
    shipped: int
    abandoned: int


class ActiveClaim(BaseModel):
    mechanic: str
    status: str
    age_hours: float


class CheckResponse(BaseModel):
    neighborhood_density: NeighborhoodDensity
    closest_active_claims: list[ActiveClaim]


class ClaimResponse(BaseModel):
    claim_id: UUID
    edit_token: str
    status: str
    timestamp: datetime


class UpdateInput(BaseModel):
    claim_id: UUID
    edit_token: str
    status: str = Field(..., pattern=r"^(shipped|abandoned)$")
    resolution_url: str | None = None


class UpdateResponse(BaseModel):
    success: bool
