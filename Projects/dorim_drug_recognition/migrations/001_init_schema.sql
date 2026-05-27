-- =============================================================================
-- Migration 001: bootstrap recognition_engine schema.
--
-- We READ from service_recognition.drugs / .bindings (operator-owned schema)
-- and OWN the recognition_engine.* tables below: normalized projections,
-- denormalized aliases, and match telemetry.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;

CREATE SCHEMA IF NOT EXISTS recognition_engine;
SET search_path TO recognition_engine, public;

-- -----------------------------------------------------------------------------
-- products: catalog projection optimized for matching.
-- One row per drug. Refreshed periodically from service_recognition.drugs.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recognition_engine.products (
    id              integer PRIMARY KEY,                         -- = service_recognition.drugs.id
    search_string   text NOT NULL,                                -- original catalog string
    normalized      text NOT NULL,                                -- normalize_text(search_string)
    mg_values       double precision[] NOT NULL DEFAULT '{}',     -- structured dose features
    ml_values       double precision[] NOT NULL DEFAULT '{}',
    g_values        double precision[] NOT NULL DEFAULT '{}',
    me_values       double precision[] NOT NULL DEFAULT '{}',
    percent_values  double precision[] NOT NULL DEFAULT '{}',
    count_n         integer,                                      -- pack count (№N)
    indexed_at      timestamptz NOT NULL DEFAULT now()
);

-- Trigram GIN index: drives candidate generation in stage 1.
-- Operator class `gin_trgm_ops` enables `%`, `<->`, similarity() etc.
CREATE INDEX IF NOT EXISTS products_normalized_trgm
    ON recognition_engine.products USING gin (normalized gin_trgm_ops);


-- -----------------------------------------------------------------------------
-- aliases: confirmed (name, maker_name) -> product_id mappings.
-- Built from service_recognition.bindings WHERE record_status_id IN (200, 210)
-- AND skipped = false AND drug_id != 0.
-- Used both as ground truth AND as an exact-match short-circuit at query time.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recognition_engine.aliases (
    id                  bigserial PRIMARY KEY,
    product_id          integer NOT NULL REFERENCES recognition_engine.products(id) ON DELETE CASCADE,
    raw_name            text NOT NULL,
    raw_maker           text NOT NULL,
    normalized_name     text NOT NULL,
    normalized_maker    text NOT NULL,
    -- Deterministic dedup key on the *normalized* pair. Different from
    -- service_recognition.bindings.hash (which hashes raw input).
    norm_hash           text GENERATED ALWAYS AS (md5(normalized_name || '|' || normalized_maker)) STORED,
    contractor_id       integer,
    source_binding_id   bigint,
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- Exact short-circuit lookup. The same (normalized_name, normalized_maker)
-- can resolve to ONE product in our golden set — we enforce this via INDEX
-- (not UNIQUE) so that historically conflicting pairs can still be ingested
-- and surfaced as a low-confidence ambiguity at query time.
CREATE INDEX IF NOT EXISTS aliases_norm_hash
    ON recognition_engine.aliases (norm_hash);

CREATE INDEX IF NOT EXISTS aliases_product_id
    ON recognition_engine.aliases (product_id);

CREATE INDEX IF NOT EXISTS aliases_normalized_trgm
    ON recognition_engine.aliases USING gin (normalized_name gin_trgm_ops);


-- -----------------------------------------------------------------------------
-- match_logs: every /match request and its top result. Used for offline
-- evaluation, error analysis, and active-learning seed for re-training.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recognition_engine.match_logs (
    id                  bigserial PRIMARY KEY,
    requested_at        timestamptz NOT NULL DEFAULT now(),
    input_name          text NOT NULL,
    input_maker         text,
    input_contractor_id integer,
    -- Resolved top-1 (may be NULL if engine returned nothing above threshold).
    top_product_id      integer,
    top_confidence      real,
    -- Full top-N JSON for later replay/eval.
    candidates          jsonb,
    -- Stage timings (ms) for performance regression tracking.
    stage_ms            jsonb,
    -- Optional human feedback later: did user accept the suggestion?
    feedback            text  -- 'accepted' | 'rejected' | 'corrected' | NULL
);

CREATE INDEX IF NOT EXISTS match_logs_requested_at
    ON recognition_engine.match_logs (requested_at DESC);
CREATE INDEX IF NOT EXISTS match_logs_top_product_id
    ON recognition_engine.match_logs (top_product_id);


-- -----------------------------------------------------------------------------
-- schema_migrations: bookkeeping (so we don't re-apply).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recognition_engine.schema_migrations (
    version    text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO recognition_engine.schema_migrations(version)
VALUES ('001_init_schema')
ON CONFLICT (version) DO NOTHING;
