"""Pydantic request / response schemas for the public API."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


def _to_percent(x: float | None) -> float | None:
    """Convert a 0..1 confidence into a 0..100 percentage rounded to 0.1.

    Single source of truth for the ``confidence`` → ``confidence_percent``
    transform used by every response model.
    """
    return None if x is None else round(x * 100, 1)


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
    components: dict[str, float] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def confidence_percent(self) -> float:
        """Same value expressed as 0..100, rounded to 0.1, for human consumers."""
        return _to_percent(self.confidence)  # type: ignore[return-value]


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


# --- /match/verify --------------------------------------------------------

class VerifyRequest(BaseModel):
    """Score a proposed (name, maker) → drug_id binding.

    All fields except ``drug_id`` and ``name`` are optional. ``external_code``
    and ``contractor_external_id`` are echoed back so the caller can pair the
    response with their internal records.
    """

    name: str = Field(..., min_length=1, max_length=500,
                      description="Contractor's product name")
    maker_name: str | None = Field(
        default=None, max_length=500,
        description="Contractor's manufacturer string",
    )
    drug_id: int = Field(..., description="Proposed product id from our catalog")
    contractor_id: int | None = Field(default=None)
    # Echo-back fields for the client's bookkeeping.
    external_code: str | None = Field(
        default=None, max_length=200,
        description="Contractor's own product code; echoed back verbatim.",
    )


class VerifyResponse(BaseModel):
    drug_id: int
    # Catalog entry corresponding to drug_id (None iff drug_id unknown).
    product_search_string: str | None
    confidence: float = Field(..., ge=0.0, le=1.0)
    components: dict[str, float] = Field(default_factory=dict)
    # See engine.VERDICT_LABELS for the full list of values.
    verdict: str
    # Human-readable Russian label for the verdict (for UI consumers).
    verdict_label: str
    alias_match: bool
    alias_conflict_with: int | None
    # What match() would choose on its own (top-1). Useful for "the engine
    # would have picked X instead, with confidence Y" UX.
    engine_top_pick: MatchCandidateOut | None = None
    stage_ms: dict[str, float] = Field(default_factory=dict)
    external_code: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def confidence_percent(self) -> float:
        return _to_percent(self.confidence)  # type: ignore[return-value]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def engine_agrees(self) -> bool:
        """True iff the engine's own top pick matches ``drug_id``."""
        return self.engine_top_pick is not None and self.engine_top_pick.product_id == self.drug_id
