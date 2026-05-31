-- =============================================================================
-- Migration 003: add structured fields parsed from catalog search_string.
--
-- Why: the maker comparison was operating on the full normalized product
-- string via partial_ratio. With a dedicated `maker_canonical` column we
-- compare the input manufacturer against ONLY the maker portion -- this
-- removes false positives where the country name (e.g. "индия") in the
-- product accidentally inflates the maker score.
-- =============================================================================

ALTER TABLE recognition_engine.products
    ADD COLUMN IF NOT EXISTS head             text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS maker_canonical  text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS country          text NOT NULL DEFAULT '';

-- Trigram index for maker-focused candidate filtering (used by future tasks).
CREATE INDEX IF NOT EXISTS products_maker_trgm_gist
    ON recognition_engine.products USING gist (maker_canonical gist_trgm_ops);

INSERT INTO recognition_engine.schema_migrations(version)
VALUES ('003_structured_fields')
ON CONFLICT (version) DO NOTHING;
