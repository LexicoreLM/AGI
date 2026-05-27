-- =============================================================================
-- Migration 002: switch products.normalized index from GIN to GiST.
--
-- Why: stage-1 candidate generation uses KNN ordering (`<->` operator) to
-- return the top-N most similar catalog entries in a single index scan.
-- GIN supports `%` membership and `similarity()` cutoffs but NOT KNN ordering;
-- the planner falls back to a Bitmap scan + sort that takes ~600ms because
-- the trigram threshold either returns too many candidates (loose) or misses
-- correct ones (strict). GiST index with `gist_trgm_ops` natively serves
-- `<->` and brings top-50 retrieval to ~25ms warm.
-- =============================================================================

CREATE INDEX IF NOT EXISTS products_normalized_trgm_gist
    ON recognition_engine.products USING gist (normalized gist_trgm_ops);

DROP INDEX IF EXISTS recognition_engine.products_normalized_trgm;

ANALYZE recognition_engine.products;

INSERT INTO recognition_engine.schema_migrations(version)
VALUES ('002_switch_to_gist')
ON CONFLICT (version) DO NOTHING;
