"""Offline evaluation of the matching engine against the golden alias set.

We sample N rows from recognition_engine.aliases, run match() with the
alias short-circuit DISABLED (so we measure genuine generalization, not
memorization of the alias table), and report:

  - top-1 accuracy : top result's product_id == ground truth
  - top-5 accuracy : ground truth among top-5
  - mean confidence on hits / misses
  - latency percentiles
  - confusion: how often the dosage variant is wrong (same drug name, wrong №)

Usage:
    uv run python scripts/evaluate.py --n 2000 --seed 42
"""

from __future__ import annotations

import argparse
import random
import statistics
import time
from collections import Counter
from typing import Sequence

from loguru import logger

from dorim_recognition.core.config import get_settings
from dorim_recognition.db.connection import raw_connection
from dorim_recognition.matching.engine import MatchQuery, get_index, match


def _sample_aliases(n: int, seed: int) -> list[dict]:
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
    rng = random.Random(seed)
    rng.shuffle(rows)
    return rows[:n]


def evaluate(n: int = 2000, seed: int = 42, top_n: int = 5) -> None:
    logger.info("warming up index...")
    get_index()
    logger.info("sampling {} test rows...", n)
    rows = _sample_aliases(n, seed)
    logger.info("got {} test rows", len(rows))

    hits_top1 = 0
    hits_topN = 0
    no_result = 0
    conf_hit: list[float] = []
    conf_miss: list[float] = []
    latencies_ms: list[float] = []

    # Breakdown of failure modes among top-1 misses.
    fail_modes: Counter[str] = Counter()

    for i, row in enumerate(rows, 1):
        t = time.perf_counter()
        res = match(
            MatchQuery(name=row["name"], maker_name=row["maker"]),
            top_n=top_n,
            use_alias_shortcircuit=False,
        )
        latencies_ms.append((time.perf_counter() - t) * 1000)

        if not res.candidates:
            no_result += 1
            continue

        truth = row["product_id"]
        top1 = res.candidates[0]
        ids = [c.product_id for c in res.candidates]

        if top1.product_id == truth:
            hits_top1 += 1
            hits_topN += 1
            conf_hit.append(top1.confidence)
        else:
            conf_miss.append(top1.confidence)
            if truth in ids:
                hits_topN += 1
                # Found within top-N: not great, but workable.
                fail_modes["top1_wrong_topN_ok"] += 1
            else:
                fail_modes["not_in_topN"] += 1

        if i % 200 == 0:
            logger.info("{} / {} processed", i, len(rows))

    total = len(rows)

    def pct(x: float) -> str:
        return f"{x * 100:.2f}%"

    def stat_line(name: str, xs: Sequence[float]) -> str:
        if not xs:
            return f"  {name:<22} n=0"
        return (
            f"  {name:<22} n={len(xs):<5} "
            f"mean={statistics.mean(xs):.3f}  "
            f"median={statistics.median(xs):.3f}  "
            f"p10={_p(xs, 10):.3f}  p90={_p(xs, 90):.3f}"
        )

    print()
    print("=" * 72)
    print(f"  Dorim recognition engine — eval on {total} held-out aliases")
    print("=" * 72)
    print(f"  top-1 accuracy        : {pct(hits_top1 / total)}  ({hits_top1}/{total})")
    print(f"  top-{top_n} accuracy        : {pct(hits_topN / total)}  ({hits_topN}/{total})")
    print(f"  no-candidate rate     : {pct(no_result / total)}  ({no_result}/{total})")
    print()
    print("  confidence:")
    print(stat_line("conf when correct", conf_hit))
    print(stat_line("conf when wrong",   conf_miss))
    print()
    print("  latency (ms):")
    print(stat_line("per-query ms",      latencies_ms))
    print()
    print("  failure modes:")
    for k, v in fail_modes.most_common():
        print(f"    {k:<25} {v}")
    print()


def _p(xs: Sequence[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    idx = max(0, min(len(s) - 1, int(round((q / 100) * (len(s) - 1)))))
    return s[idx]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=2000, help="number of test rows")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--top-n", type=int, default=5)
    args = p.parse_args()
    evaluate(n=args.n, seed=args.seed, top_n=args.top_n)


if __name__ == "__main__":
    main()
