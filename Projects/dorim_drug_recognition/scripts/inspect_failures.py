"""Inspect failure cases from the matching engine.

Re-runs the evaluation on a deterministic sample and prints the top-K worst
predictions so we can identify systematic issues (data quality, normalization,
weighting).
"""

from __future__ import annotations

import argparse
import random

from loguru import logger

from dorim_recognition.core.config import get_settings
from dorim_recognition.db.connection import raw_connection
from dorim_recognition.matching.engine import MatchQuery, get_index, match


def _sample(n: int, seed: int) -> list[dict]:
    settings = get_settings()
    with raw_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT raw_name AS name, raw_maker AS maker, product_id "
                f"FROM {settings.engine_schema}.aliases TABLESAMPLE SYSTEM (10) "
                f"LIMIT %s",
                (n * 3,),
            )
            rows = cur.fetchall()
    random.Random(seed).shuffle(rows)
    return rows[:n]


def _product(conn, settings, pid: int) -> str:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT search_string FROM {settings.engine_schema}.products WHERE id = %s",
            (pid,),
        )
        r = cur.fetchone()
    return r["search_string"] if r else "?"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=500)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--show", type=int, default=20, help="how many failures to print")
    args = p.parse_args()

    get_index()
    settings = get_settings()
    rows = _sample(args.n, args.seed)
    logger.info("evaluating {} rows...", len(rows))

    failures = []
    with raw_connection(autocommit=True) as conn:
        for row in rows:
            res = match(
                MatchQuery(name=row["name"], maker_name=row["maker"]),
                top_n=5,
                use_alias_shortcircuit=False,
            )
            if not res.candidates:
                continue
            ids = [c.product_id for c in res.candidates]
            if row["product_id"] not in ids:
                failures.append({
                    "name": row["name"],
                    "maker": row["maker"],
                    "truth_id": row["product_id"],
                    "truth_str": _product(conn, settings, row["product_id"]),
                    "top1": res.candidates[0],
                })

        print(f"\nTotal failures (truth not in top-5): {len(failures)}\n")
        for i, f in enumerate(failures[: args.show], 1):
            print(f"--- #{i} -------------------------------------------------------------")
            print(f"  INPUT     name : {f['name']!r}")
            print(f"            maker: {f['maker']!r}")
            print(f"  TRUTH    #{f['truth_id']}  {f['truth_str']}")
            top = f["top1"]
            print(f"  PRED  #{top.product_id} ({top.confidence:.2f})  {top.search_string}")
            print(f"            comp: {top.components}")


if __name__ == "__main__":
    main()
