"""Pydantic request / response schemas for the public API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MatchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=500, description="Raw product name")
    maker_name: str | None = Field(default=None, max_length=500, description="Raw manufacturer / country")
    contractor_id: int | None = Field(default=None, description="Optional contractor identifier")
    top_n: int = Field(default=5, ge=1, le=50)


class MatchCandidateOut(BaseModel):
    product_id: int
    search_string: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    components: dict[str, float] = Field(default_factory=dict)


class MatchResponse(BaseModel):
    candidates: list[MatchCandidateOut]
    exact_alias_hit: bool = False
    stage_ms: dict[str, float] = Field(default_factory=dict)


class BatchRow(BaseModel):
    """A single row from an uploaded batch file."""

    name: str
    maker_name: str | None = None
    contractor_id: int | None = None


class HealthResponse(BaseModel):
    status: str
    catalog_size: int
    aliases_size: int
