"""Batch file processing: read xlsx/csv -> match -> write xlsx with results."""

from __future__ import annotations

import io
from typing import Callable

import pandas as pd
from loguru import logger

from dorim_recognition.matching.engine import MatchQuery, match, match_batch


# Column name aliases (lowercase) — we try several to be tolerant of input layouts.
_NAME_COLS = ("name", "product_name", "название", "наименование", "товар")
_MAKER_COLS = ("maker", "maker_name", "manufacturer", "производитель", "изготовитель")
_CONTRACTOR_COLS = ("contractor_id", "contractor", "контрагент")
# External product code provided by the caller — preserved verbatim and echoed
# back in the output as the canonical column ``external_code``.
_EXT_CODE_COLS = (
    "external_code", "external_id", "external", "артикул",
    "код", "код товара", "товар_код", "sku", "id_external",
)


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


def process_dataframe(
    df: pd.DataFrame,
    *,
    top_n: int = 3,
    progress_cb: Callable[[int, int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> pd.DataFrame:
    """Run matching for every row and return a DataFrame with augmented columns.

    ``progress_cb(processed, total)`` is invoked periodically (~every 1% of
    rows) with cumulative counts -- used by the async job runner to update
    progress without coupling to it.

    ``cancel_cb()`` is polled at the same cadence; if it returns True we
    stop early and return whatever rows have been processed so far. The
    caller is responsible for raising / propagating the cancellation status.
    """
    name_col = _pick_column(df, _NAME_COLS)
    if name_col is None:
        raise ValueError(
            f"Input file must contain one of name columns: {_NAME_COLS}. "
            f"Got: {list(df.columns)}"
        )
    maker_col = _pick_column(df, _MAKER_COLS)
    contractor_col = _pick_column(df, _CONTRACTOR_COLS)
    ext_code_col = _pick_column(df, _EXT_CODE_COLS)

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

    total = len(queries)
    logger.info("batch: processing {} rows (top_n={})", total, top_n)

    # Streaming match loop so we can report progress.
    # We deliberately don't call match_batch() in one shot any more.
    records = df.to_dict(orient="records")
    out_records: list[dict] = []
    # Report at most ~100 times for any size of input (1% granularity).
    step = max(1, total // 100)
    for i, (src, q) in enumerate(zip(records, queries, strict=True), 1):
        res = match(q, top_n=top_n)
        rec = dict(src)
        # Promote external code to the canonical key so consumers don't have
        # to know which alias was used in the input (артикул / sku / ...).
        if ext_code_col and ext_code_col != "external_code":
            val = rec.get(ext_code_col)
            if val is not None and (not isinstance(val, float) or not pd.isna(val)):
                rec["external_code"] = val
        top = res.candidates[0] if res.candidates else None
        rec["matched_product_id"] = top.product_id if top else None
        rec["matched_search_string"] = top.search_string if top else None
        rec["confidence"] = top.confidence if top else 0.0
        rec["confidence_percent"] = round((top.confidence if top else 0.0) * 100, 1)
        rec["exact_alias_hit"] = res.exact_alias_hit
        for j in range(1, top_n):
            cand = res.candidates[j] if len(res.candidates) > j else None
            rec[f"alt_{j}_id"] = cand.product_id if cand else None
            rec[f"alt_{j}_search_string"] = cand.search_string if cand else None
            rec[f"alt_{j}_confidence"] = cand.confidence if cand else None
            rec[f"alt_{j}_confidence_percent"] = (
                round(cand.confidence * 100, 1) if cand else None
            )
        out_records.append(rec)

        if i % step == 0 or i == total:
            if progress_cb is not None:
                progress_cb(i, total)
            if cancel_cb is not None and cancel_cb():
                logger.info("batch cancelled at row {}/{}", i, total)
                break

    return pd.DataFrame(out_records)


def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to xlsx bytes.

    Percentage columns (anything matching ``*_percent`` or already named with
    ``%``) get an Excel cell format of ``0.0"%"`` so the visible value is
    e.g. "95.0%" while the underlying numeric value (95.0) is preserved for
    sorting / filtering / formulas.
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="matches")
        ws = writer.sheets["matches"]
        # Identify percent columns by name.
        percent_cols: list[int] = []
        for idx, name in enumerate(df.columns, start=1):
            lname = str(name).lower()
            if lname.endswith("_percent") or "точность %" in lname or "вероятность %" in lname:
                percent_cols.append(idx)
        if percent_cols:
            # Apply number format to every data row in those columns.
            from openpyxl.utils import get_column_letter
            for col_idx in percent_cols:
                letter = get_column_letter(col_idx)
                # Skip header (row 1); apply to all data rows.
                for row in range(2, ws.max_row + 1):
                    ws[f"{letter}{row}"].number_format = '0.0"%"'
        # Auto-size width heuristic: cap at 60 chars to keep things readable.
        from openpyxl.utils import get_column_letter
        for idx, name in enumerate(df.columns, start=1):
            letter = get_column_letter(idx)
            sample = df.iloc[:, idx - 1].head(100).tolist()
            max_len = max([len(str(name))] + [len(str(v)) for v in sample])
            ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 60)
    buf.seek(0)
    return buf.getvalue()


def process_stream(
    file_bytes: bytes,
    filename: str,
    *,
    top_n: int = 3,
    progress_cb: Callable[[int, int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[bytes, str, bool]:
    """End-to-end: bytes in -> xlsx bytes out + output filename + cancelled flag."""
    df = read_input(file_bytes, filename)
    result_df = process_dataframe(
        df, top_n=top_n, progress_cb=progress_cb, cancel_cb=cancel_cb,
    )
    out_bytes = to_xlsx_bytes(result_df)
    base = filename.rsplit(".", 1)[0]
    # If the result has fewer rows than the input, the run was cancelled mid-loop.
    cancelled = len(result_df) < len(df)
    return out_bytes, f"{base}__matched.xlsx", cancelled
