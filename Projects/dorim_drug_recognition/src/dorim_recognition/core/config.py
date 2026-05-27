"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings.

    Loaded from environment or .env file. All values can be overridden
    by setting `DORIM_<UPPER_KEY>` environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DORIM_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ----------------------------------------------------------------
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "agent"
    db_password: str = "pass"
    db_name: str = "service_recognition"
    # Schema where we read source data from (existing operator schema).
    source_schema: str = "service_recognition"
    # Schema where we own all engine-specific tables.
    engine_schema: str = "recognition_engine"

    # --- Matching engine ---------------------------------------------------------
    # Candidate generation: how many trigram candidates to fetch from PG before reranking.
    # 500 gives top-5 recall ~92% on held-out aliases; raising further has diminishing returns.
    candidate_limit: int = 500
    # TF-IDF n-gram range for character ngrams.
    tfidf_ngram_min: int = 3
    tfidf_ngram_max: int = 5
    # Hybrid score weights (must sum to 1.0).
    w_fuzzy: float = 0.40
    w_tfidf: float = 0.30
    w_maker: float = 0.20
    w_dosage: float = 0.10
    # Confidence threshold below which we tag the result as "low_confidence".
    low_confidence_threshold: float = 0.55

    # --- API ---------------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1
    # Max batch file size in MB.
    max_upload_mb: int = 50

    # --- Logging -----------------------------------------------------------------
    log_level: str = "INFO"

    @property
    def sqlalchemy_url(self) -> str:
        """SQLAlchemy DSN for psycopg v3 driver."""
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def psycopg_url(self) -> str:
        """Plain DSN for raw psycopg connections."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
