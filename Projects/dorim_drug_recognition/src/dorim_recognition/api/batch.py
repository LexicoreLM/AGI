"""Batch file processing: read xlsx/csv -> match -> write xlsx with results."""

from __future__ import annotations

import io
from typing import BinaryIO

import pandas as pd
from loguru import logger

from dorim_recognition.matching.engine import MatchQuery, match_batch


# Column name aliases (lowercase) — we try several to be tolerant of input layouts.
_NAME_COLS = ("name", "product_name", "название", "наименование", "товар")
_MAKER_COLS = ("maker", "maker_name", "manufacturer", "производитель", "изготовитель")
_CONTRACTOR_COLS = ("contractor_id", "contractor", "контрагент")


def _pick_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    lookup = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in lookup:
            return lookup[cand]
    return None


def read_input(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Read an uploaded file (xlsx/xls/csv) into a DataFrame."""
    name_lower = filename.lower()
    bio = io.BytesIO(file_bytes)
    if name_lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(bio, dtype=str)
    if name_lower.endswith((".csv", ".tsv")):
        sep = "\t" if name_lower.endswith(".tsv") else None
        return pd.read_csv(bio, dtype=str, sep=sep, engine="python")
    raise ValueError(f"Unsupported file extension: {filename}")


def process_dataframe(df: pd.DataFrame, *, top_n: int = 3) -> pd.DataFrame:
    """Run matching for every row and return a DataFrame with augmented columns."""
    name_col = _pick_column(df, _NAME_COLS)
    if name_col is None:
        raise ValueError(
            f"Input file must contain one of name columns: {_NAME_COLS}. "
            f"Got: {list(df.columns)}"
        )
    maker_col = _pick_column(df, _MAKER_COLS)
    contractor_col = _pick_column(df, _CONTRACTOR_COLS)

    queries: list[MatchQuery] = []
    for _, row in df.iterrows():
        name = (row[name_col] or "") if pd.notna(row[name_col]) else ""
        maker = ""
        if maker_col and pd.notna(row[maker_col]):
            maker = row[maker_col] or ""
        contractor_id = None
        if contractor_col and pd.notna(row[contractor_col]):
            try:
                contractor_id = int(row[contractor_col])
            except (TypeError, ValueError):
                contractor_id = None
        queries.append(MatchQuery(name=name, maker_name=maker, contractor_id=contractor_id))

    logger.info("batch: processing {} rows (top_n={})", len(queries), top_n)
    results = match_batch(queries, top_n=top_n)

    # Flatten: for each input row produce columns
    #   matched_product_id, matched_search_string, confidence, exact_alias_hit,
    # plus top_2_id / top_2_confidence / top_3_id / top_3_confidence (configurable).
    out_records = []
    for src, res in zip(df.to_dict(orient="records"), results, strict=True):
        rec = dict(src)
        top = res.candidates[0] if res.candidates else None
        rec["matched_product_id"] = top.product_id if top else None
        rec["matched_search_string"] = top.search_string if top else None
        rec["confidence"] = top.confidence if top else 0.0
        rec["exact_alias_hit"] = res.exact_alias_hit
        for i in range(1, top_n):
            cand = res.candidates[i] if len(res.candidates) > i else None
            rec[f"alt_{i}_id"] = cand.product_id if cand else None
            rec[f"alt_{i}_search_string"] = cand.search_string if cand else None
            rec[f"alt_{i}_confidence"] = cand.confidence if cand else None
        out_records.append(rec)

    return pd.DataFrame(out_records)


def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to xlsx bytes."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="matches")
    buf.seek(0)
    return buf.getvalue()


def process_stream(file_bytes: bytes, filename: str, *, top_n: int = 3) -> tuple[bytes, str]:
    """End-to-end: bytes in -> xlsx bytes out + output filename."""
    df = read_input(file_bytes, filename)
    result_df = process_dataframe(df, top_n=top_n)
    out_bytes = to_xlsx_bytes(result_df)
    base = filename.rsplit(".", 1)[0]
    return out_bytes, f"{base}__matched.xlsx"
