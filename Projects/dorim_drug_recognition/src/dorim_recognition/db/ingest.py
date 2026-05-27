"""Ingest source data into recognition_engine.* tables.

- ``ingest_products()`` rebuilds recognition_engine.products from
  service_recognition.drugs. Idempotent (TRUNCATE + INSERT).
- ``ingest_aliases()`` rebuilds recognition_engine.aliases from "golden"
  bindings (status IN (200, 210), not skipped, drug_id != 0, and the
  drug_id exists in our products table).

Throughput strategy: load source into memory (datasets are small enough --
72.5K drugs / ~10MB and 515K aliases / ~80MB), then write via psycopg's
``COPY ... FROM STDIN`` for ~10x speed vs. executemany.
"""

from __future__ import annotations

import io
import sys
from typing import Iterable

from loguru import logger

from dorim_recognition.core.config import get_settings
from dorim_recognition.db.connection import raw_connection
from dorim_recognition.matching.normalize import (
    extract_dosage_features,
    normalize_maker,
    normalize_text,
)


def _pg_float_array(xs: Iterable[float]) -> str:
    """Serialize floats to a PostgreSQL array literal (``{1.0,2.5}``)."""
    return "{" + ",".join(f"{x:g}" for x in xs) + "}"


def _copy_field(s: object) -> str:
    """Escape a single field for PostgreSQL text-format COPY."""
    if s is None:
        return r"\N"
    text = str(s)
    return (
        text.replace("\\", "\\\\")
            .replace("\t", "\\t")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
    )


def _copy_line(*fields: object) -> str:
    return "\t".join(_copy_field(f) for f in fields) + "\n"


# -----------------------------------------------------------------------------
# Products
# -----------------------------------------------------------------------------

def ingest_products() -> int:
    """Rebuild products table. Returns number of rows inserted."""
    settings = get_settings()

    # Read all source drugs into memory.
    logger.info("products: reading source...")
    with raw_connection(autocommit=True) as src:
        with src.cursor() as cur:
            cur.execute(
                f"SELECT id, search_string FROM {settings.source_schema}.drugs ORDER BY id"
            )
            rows = cur.fetchall()
    logger.info("products: loaded {} source rows", len(rows))

    # Build COPY payload in memory.
    buf = io.StringIO()
    for r in rows:
        drug_id = r["id"]
        search_string = r["search_string"] or ""
        normalized = normalize_text(search_string)
        feats = extract_dosage_features(normalized)
        buf.write(_copy_line(
            drug_id,
            search_string,
            normalized,
            _pg_float_array(sorted(feats.mg)),
            _pg_float_array(sorted(feats.ml)),
            _pg_float_array(sorted(feats.g)),
            _pg_float_array(sorted(feats.me)),
            _pg_float_array(sorted(feats.percent)),
            feats.count,
        ))
    payload = buf.getvalue()

    with raw_connection(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE {settings.engine_schema}.products RESTART IDENTITY CASCADE")
            copy_sql = (
                f"COPY {settings.engine_schema}.products "
                "(id, search_string, normalized, mg_values, ml_values, g_values, "
                "me_values, percent_values, count_n) FROM STDIN"
            )
            with cur.copy(copy_sql) as cp:
                cp.write(payload)
        conn.commit()

    logger.success("products: ingested {}", len(rows))
    return len(rows)


# -----------------------------------------------------------------------------
# Aliases
# -----------------------------------------------------------------------------

def ingest_aliases() -> int:
    """Rebuild aliases table from golden bindings."""
    settings = get_settings()

    logger.info("aliases: reading source (golden bindings)...")
    sql = f"""
        SELECT b.id, b.name, b.maker_name, b.contractor_id, b.drug_id
        FROM {settings.source_schema}.bindings b
        JOIN {settings.engine_schema}.products p ON p.id = b.drug_id
        WHERE b.record_status_id IN (200, 210)
          AND b.skipped = false
          AND b.drug_id <> 0
        ORDER BY b.id
    """
    with raw_connection(autocommit=True) as src:
        with src.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    logger.info("aliases: loaded {} source rows", len(rows))

    buf = io.StringIO()
    written = 0
    for r in rows:
        raw_name = r["name"] or ""
        raw_maker = r["maker_name"] or ""
        n_name = normalize_text(raw_name)
        if not n_name:
            continue
        n_maker = normalize_maker(raw_maker)
        buf.write(_copy_line(
            r["drug_id"],
            raw_name,
            raw_maker,
            n_name,
            n_maker,
            r["contractor_id"],
            r["id"],
        ))
        written += 1
    payload = buf.getvalue()

    with raw_connection(autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE {settings.engine_schema}.aliases RESTART IDENTITY CASCADE")
            copy_sql = (
                f"COPY {settings.engine_schema}.aliases "
                "(product_id, raw_name, raw_maker, normalized_name, normalized_maker, "
                "contractor_id, source_binding_id) FROM STDIN"
            )
            with cur.copy(copy_sql) as cp:
                cp.write(payload)
        # Refresh planner stats so the GIN index gets used.
        with conn.cursor() as cur:
            cur.execute(f"ANALYZE {settings.engine_schema}.products")
            cur.execute(f"ANALYZE {settings.engine_schema}.aliases")
        conn.commit()

    logger.success("aliases: ingested {}", written)
    return written


def main() -> None:
    try:
        ingest_products()
        ingest_aliases()
    except Exception as exc:
        logger.exception("ingest failed: {}", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
