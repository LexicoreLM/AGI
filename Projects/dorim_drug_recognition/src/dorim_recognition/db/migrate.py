"""Apply SQL migrations from the migrations/ directory in lexical order.

Tracked in recognition_engine.schema_migrations. Idempotent: re-running the
script will skip already-applied versions.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from dorim_recognition.db.connection import raw_connection


MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def _already_applied(conn) -> set[str]:
    with conn.cursor() as cur:
        # If schema doesn't exist yet, table doesn't either — return empty.
        cur.execute(
            "SELECT to_regclass('recognition_engine.schema_migrations') IS NOT NULL AS exists"
        )
        row = cur.fetchone()
        if not row or not row["exists"]:
            return set()
        cur.execute("SELECT version FROM recognition_engine.schema_migrations")
        return {r["version"] for r in cur.fetchall()}


def apply_migrations() -> None:
    if not MIGRATIONS_DIR.exists():
        logger.warning("Migrations directory not found: {}", MIGRATIONS_DIR)
        return

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        logger.warning("No migration files found in {}", MIGRATIONS_DIR)
        return

    with raw_connection(autocommit=False) as conn:
        applied = _already_applied(conn)
        for path in files:
            version = path.stem
            if version in applied:
                logger.info("skip {} (already applied)", version)
                continue
            logger.info("apply {}", version)
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            logger.success("applied {}", version)


def main() -> None:
    try:
        apply_migrations()
    except Exception as exc:
        logger.exception("migration failed: {}", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
