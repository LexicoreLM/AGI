"""Pydantic request / response schemas for the public API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MatchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=500, description="Raw product name")
    maker_name: str | None = Field(default=None, max_length=500, description="Raw manufacturer / country")
    contractor_id: int | None = Field(default=None, description="Optional contractor identifier")
    # Caller-supplied product identifier (article, SKU, internal id). Not used
    # for matching; echoed back verbatim in the response so the client can
    # round-trip its own ids without bookkeeping.
    external_code: str | None = Field(
        default=None, max_length=200,
        description="Caller's product code (артикул / SKU). Echoed back in the response.",
    )
    top_n: int = Field(default=5, ge=1, le=50)


class MatchCandidateOut(BaseModel):
    product_id: int
    search_string: str
    # Canonical 0..1 value -- machine-friendly, exact.
    confidence: float = Field(..., ge=0.0, le=1.0)
    # Same value expressed as a percentage (0..100, one decimal place) for
    # human-readable consumers (UI, reports). Derived from ``confidence``.
    confidence_percent: float = Field(..., ge=0.0, le=100.0)
    components: dict[str, float] = Field(default_factory=dict)


class MatchResponse(BaseModel):
    candidates: list[MatchCandidateOut]
    exact_alias_hit: bool = False
    stage_ms: dict[str, float] = Field(default_factory=dict)
    # Echoed verbatim from the request, when provided.
    external_code: str | None = None


class BatchRow(BaseModel):
    """A single row from an uploaded batch file."""

    name: str
    maker_name: str | None = None
    contractor_id: int | None = None


class HealthResponse(BaseModel):
    status: str
    catalog_size: int
    aliases_size: int
