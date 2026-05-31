"""Analyze a batch output xlsx: confidence distribution, hit-rate per pattern,
add human-readable RU column aliases. Writes an analyzed.xlsx and prints a
text report."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def analyze(in_path: Path, out_path: Path) -> None:
    df = pd.read_excel(in_path)

    print(f"Файл: {in_path.name}")
    print(f"Строк всего: {len(df)}")
    print()

    # --- Distribution of confidence (top-1) ----------------------------------
    bins = [0, 0.4, 0.55, 0.7, 0.85, 1.01]
    labels = ["<40% (мусор)", "40-55% (низкая)", "55-70% (средняя)",
              "70-85% (высокая)", "≥85% (точная)"]
    counts = pd.cut(df["confidence"], bins=bins, labels=labels, right=False)
    dist = counts.value_counts().reindex(labels, fill_value=0)
    print("Распределение confidence (top-1):")
    for label, n in dist.items():
        pct = n / len(df) * 100
        bar = "█" * int(pct / 2)
        print(f"  {label:<20} {n:>4}  {pct:>5.1f}%  {bar}")
    print()

    exact = int(df["exact_alias_hit"].sum())
    print(f"Exact alias hits (мгновенные, conf=0.99): {exact} ({exact/len(df)*100:.1f}%)")
    print()

    # --- Per-pattern breakdown (group by the input "name" with numeric suffix stripped) -
    df["_pattern"] = df["name"].astype(str).str.replace(r"\s+\d+$", "", regex=True)
    grp = df.groupby("_pattern").agg(
        rows=("name", "size"),
        conf_mean=("confidence", "mean"),
        conf_min=("confidence", "min"),
        conf_max=("confidence", "max"),
        exact_hits=("exact_alias_hit", "sum"),
    ).round(3).sort_values("conf_mean", ascending=False)
    print("Разбивка по шаблону входа (top-1 confidence):")
    print(grp.to_string())
    print()

    # --- Most common top-1 catalog matches per pattern -----------------------
    print("Самые частые совпадения по каждому шаблону:")
    for pat, sub in df.groupby("_pattern"):
        top = sub["matched_search_string"].value_counts().head(3)
        mean_conf = sub["confidence"].mean()
        print(f"\n  [{pat!r}] средний conf = {mean_conf:.3f}")
        for s, n in top.items():
            print(f"     {n:>3}× ({n/len(sub)*100:>4.0f}%)  {s[:80]}")

    # --- Threshold analysis ---------------------------------------------------
    print()
    print("Сколько строк проходят порог уверенности:")
    for thr in (0.55, 0.65, 0.75, 0.85):
        n = int((df["confidence"] >= thr).sum())
        print(f"  conf ≥ {thr:.2f}:  {n:>4}  ({n/len(df)*100:>5.1f}%)")

    # --- Build a readable copy with Russian column aliases ------------------
    df = df.drop(columns=["_pattern"])
    maker_col = "maker_name" if "maker_name" in df.columns else (
        "maker" if "maker" in df.columns else None
    )
    cols: dict[str, pd.Series] = {}
    # External code first (when present) so operators see their own ID up front.
    if "external_code" in df.columns:
        cols["Внешний код"] = df["external_code"]
    cols["Название (вход)"]         = df["name"]
    if maker_col:
        cols["Производитель (вход)"] = df[maker_col]
    cols["Самый релевантный товар"] = df["matched_search_string"]
    cols["ID товара"]               = df["matched_product_id"]
    cols["Точность (%)"]            = (df["confidence"] * 100).round(1)
    cols["Точное совпадение"]       = df["exact_alias_hit"].map({True: "✓", False: ""})
    if "alt_1_search_string" in df.columns:
        cols["Альт. 1 — товар"]      = df["alt_1_search_string"]
        cols["Альт. 1 — точность %"] = (df["alt_1_confidence"] * 100).round(1)
    if "alt_2_search_string" in df.columns:
        cols["Альт. 2 — товар"]      = df["alt_2_search_string"]
        cols["Альт. 2 — точность %"] = (df["alt_2_confidence"] * 100).round(1)
    ru = pd.DataFrame(cols)
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        ru.to_excel(w, index=False, sheet_name="результаты")
    print()
    print(f"Расширенный файл с понятными колонками: {out_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None)
    args = p.parse_args()
    out = args.output or args.input.with_name(args.input.stem + "__analyzed.xlsx")
    analyze(args.input, out)


if __name__ == "__main__":
    main()
