"""Hybrid matching engine.

Pipeline for a single (name, maker_name) query:

  Stage 0 — Exact alias short-circuit
    Hash normalized (name + maker) and probe recognition_engine.aliases.
    If a unique product_id is returned, score = 0.99 and we stop.

  Stage 1 — Candidate generation (trigram KNN)
    PostgreSQL GiST trigram index returns the top-N products ordered by
    `normalized <-> query`. Typical N = 200. Fast (~30ms warm).

  Stage 2 — Rerank
    For each candidate compute a hybrid score:
      score = w_fuzzy   * rapidfuzz.token_set_ratio(name, product) / 100
            + w_tfidf   * cosine(TF-IDF char-ngrams)
            + w_maker   * maker similarity (rapidfuzz.partial_ratio)
            + w_dosage  * dosage_similarity(features_a, features_b)

  Stage 3 — Calibration & ordering
    Sort by score descending, take top-N. Score is already in [0,1]; we
    expose it as a "probability" in the API response.

The TF-IDF vectorizer is fitted lazily on the catalog at first use and
cached in memory (the vectorizer + the catalog matrix). For 72.5K rows
of short strings the matrix is ~30MB sparse — comfortable for a single
process.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Sequence

import numpy as np
from loguru import logger
from rapidfuzz import fuzz
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize as l2_normalize

from dorim_recognition.core.config import Settings, get_settings
from dorim_recognition.db.connection import raw_connection
from dorim_recognition.matching.normalize import (
    DosageFeatures,
    dosage_similarity,
    extract_dosage_features,
    normalize_maker,
    normalize_text,
)


# -----------------------------------------------------------------------------
# Data classes
# -----------------------------------------------------------------------------

@dataclass
class MatchCandidate:
    """A single result row returned to the caller."""

    product_id: int
    search_string: str
    confidence: float
    # Per-component scores so the UI / debugger can show why a result ranked high.
    components: dict[str, float] = field(default_factory=dict)


@dataclass
class MatchQuery:
    name: str
    maker_name: str | None = None
    contractor_id: int | None = None


@dataclass
class MatchResult:
    candidates: list[MatchCandidate]
    stage_ms: dict[str, float]
    exact_alias_hit: bool = False


# -----------------------------------------------------------------------------
# Index cache: catalog + TF-IDF
# -----------------------------------------------------------------------------

@dataclass
class _CatalogIndex:
    """All in-memory artifacts needed for matching."""

    product_ids: np.ndarray  # shape (N,)
    search_strings: list[str]
    normalized: list[str]
    dose_features: list[DosageFeatures]
    id_to_pos: dict[int, int]
    vectorizer: TfidfVectorizer
    tfidf_matrix: sparse.csr_matrix  # shape (N, V), L2-normalized rows


_INDEX: _CatalogIndex | None = None
_INDEX_LOCK = Lock()


def _build_index() -> _CatalogIndex:
    """Load products from DB and fit the TF-IDF vectorizer.

    Called once at startup (or lazily on first /match). The CPU cost is
    dominated by the vectorizer fit + transform: ~2-4 seconds for 72.5K
    short strings, with the resulting CSR matrix at ~30MB.
    """
    logger.info("building catalog index...")
    settings = get_settings()
    t0 = time.perf_counter()

    with raw_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, search_string, normalized, mg_values, ml_values, g_values, "
                f"me_values, percent_values, count_n "
                f"FROM {settings.engine_schema}.products ORDER BY id"
            )
            rows = cur.fetchall()

    product_ids = np.array([r["id"] for r in rows], dtype=np.int64)
    search_strings = [r["search_string"] for r in rows]
    normalized = [r["normalized"] for r in rows]
    dose_features = [
        DosageFeatures(
            mg=frozenset(r["mg_values"] or ()),
            ml=frozenset(r["ml_values"] or ()),
            g=frozenset(r["g_values"] or ()),
            me=frozenset(r["me_values"] or ()),
            percent=frozenset(r["percent_values"] or ()),
            count=r["count_n"],
            volume_ml=None,
        )
        for r in rows
    ]
    id_to_pos = {pid: i for i, pid in enumerate(product_ids.tolist())}

    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(settings.tfidf_ngram_min, settings.tfidf_ngram_max),
        min_df=2,
        sublinear_tf=True,
        norm=None,  # we apply L2 ourselves so we can also normalize the query
        dtype=np.float32,
    )
    matrix = vectorizer.fit_transform(normalized)
    matrix = l2_normalize(matrix, norm="l2", copy=False)

    t1 = time.perf_counter()
    logger.success(
        "index built: {} products, vocab={}, matrix={} bytes, took {:.2f}s",
        len(product_ids),
        len(vectorizer.vocabulary_),
        matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes,
        t1 - t0,
    )

    return _CatalogIndex(
        product_ids=product_ids,
        search_strings=search_strings,
        normalized=normalized,
        dose_features=dose_features,
        id_to_pos=id_to_pos,
        vectorizer=vectorizer,
        tfidf_matrix=matrix,
    )


def get_index() -> _CatalogIndex:
    """Thread-safe lazy initializer."""
    global _INDEX
    if _INDEX is None:
        with _INDEX_LOCK:
            if _INDEX is None:
                _INDEX = _build_index()
    return _INDEX


def reset_index() -> None:
    """Drop the cached index (used after re-ingest)."""
    global _INDEX
    with _INDEX_LOCK:
        _INDEX = None


# -----------------------------------------------------------------------------
# Stage 0 — exact alias short-circuit
# -----------------------------------------------------------------------------

def _alias_hash(normalized_name: str, normalized_maker: str) -> str:
    return hashlib.md5(f"{normalized_name}|{normalized_maker}".encode()).hexdigest()


def _alias_short_circuit(
    conn, settings: Settings, n_name: str, n_maker: str
) -> int | None:
    """Return product_id iff the (name, maker) is known unambiguously."""
    h = _alias_hash(n_name, n_maker)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT product_id, COUNT(*) AS c "
            f"FROM {settings.engine_schema}.aliases "
            f"WHERE norm_hash = %s GROUP BY product_id",
            (h,),
        )
        rows = cur.fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]["product_id"]
    # Ambiguous: same input mapped to multiple products historically.
    # We refuse the short-circuit and fall back to ranking.
    return None


# -----------------------------------------------------------------------------
# Stage 1 — trigram candidate generation
# -----------------------------------------------------------------------------

def _trigram_candidates(
    conn, settings: Settings, n_name: str, limit: int
) -> list[int]:
    """Return product_ids ordered by trigram distance to n_name (ascending)."""
    sql = (
        f"SELECT id FROM {settings.engine_schema}.products "
        f"ORDER BY normalized <-> %s LIMIT %s"
    )
    with conn.cursor() as cur:
        cur.execute(sql, (n_name, limit))
        return [r["id"] for r in cur.fetchall()]


# -----------------------------------------------------------------------------
# Stage 2 — rerank
# -----------------------------------------------------------------------------

def _rerank(
    index: _CatalogIndex,
    settings: Settings,
    candidate_ids: Sequence[int],
    n_name: str,
    n_maker: str,
    query_features: DosageFeatures,
    top_n: int,
) -> list[MatchCandidate]:
    if not candidate_ids:
        return []

    positions = np.array(
        [index.id_to_pos[c] for c in candidate_ids if c in index.id_to_pos],
        dtype=np.int64,
    )
    if positions.size == 0:
        return []

    # --- TF-IDF cosine: vectorize the query and dot with candidate sub-matrix.
    query_vec = index.vectorizer.transform([n_name])
    query_vec = l2_normalize(query_vec, norm="l2", copy=False)
    # tfidf_matrix is L2-normalized -> dot product == cosine.
    sub = index.tfidf_matrix[positions]
    cos_scores = (sub @ query_vec.T).toarray().ravel()  # shape (K,)

    # --- Fuzzy on the full normalized string (token-set is robust to reorder).
    # --- Maker fuzzy (partial_ratio is permissive about extra country tails).
    # --- Dosage structured similarity.
    n_makers = [index.normalized[p] for p in positions]
    fuzzy_scores = np.empty(positions.size, dtype=np.float32)
    maker_scores = np.empty(positions.size, dtype=np.float32)
    dose_scores = np.empty(positions.size, dtype=np.float32)
    for i, p in enumerate(positions):
        product_norm = index.normalized[p]
        fuzzy_scores[i] = fuzz.token_set_ratio(n_name, product_norm) / 100.0
        if n_maker:
            # Compare query maker against the FULL product string -- the maker
            # token usually lives inside it (e.g. "...dr.reddy's индия").
            maker_scores[i] = fuzz.partial_ratio(n_maker, product_norm) / 100.0
        else:
            maker_scores[i] = 0.5  # neutral if no maker provided
        dose_scores[i] = dosage_similarity(query_features, index.dose_features[p])

    final = (
        settings.w_fuzzy * fuzzy_scores
        + settings.w_tfidf * cos_scores
        + settings.w_maker * maker_scores
        + settings.w_dosage * dose_scores
    )

    # Pick top-N by final score.
    if positions.size > top_n:
        top_idx = np.argpartition(-final, top_n - 1)[:top_n]
        top_idx = top_idx[np.argsort(-final[top_idx])]
    else:
        top_idx = np.argsort(-final)

    out: list[MatchCandidate] = []
    for j in top_idx:
        p = int(positions[j])
        out.append(MatchCandidate(
            product_id=int(index.product_ids[p]),
            search_string=index.search_strings[p],
            confidence=float(round(final[j], 4)),
            components={
                "fuzzy": float(round(fuzzy_scores[j], 4)),
                "tfidf": float(round(cos_scores[j], 4)),
                "maker": float(round(maker_scores[j], 4)),
                "dosage": float(round(dose_scores[j], 4)),
            },
        ))
    return out


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def match(
    query: MatchQuery,
    *,
    top_n: int = 5,
    use_alias_shortcircuit: bool = True,
) -> MatchResult:
    """Match a single (name, maker_name) query and return up to top_n candidates.

    ``use_alias_shortcircuit=False`` disables stage 0 — used by offline
    evaluation to measure pure recall of the trigram+rerank pipeline (otherwise
    evaluating on data that lives in the alias table just measures memorization).
    """
    settings = get_settings()
    index = get_index()

    n_name = normalize_text(query.name)
    n_maker = normalize_maker(query.maker_name) if query.maker_name else ""
    q_feats = extract_dosage_features(n_name)

    timings: dict[str, float] = {}

    if not n_name:
        return MatchResult(candidates=[], stage_ms=timings)

    with raw_connection(autocommit=True) as conn:
        if use_alias_shortcircuit:
            # --- Stage 0 ---
            t = time.perf_counter()
            product_id = _alias_short_circuit(conn, settings, n_name, n_maker)
            timings["alias"] = (time.perf_counter() - t) * 1000

            if product_id is not None and product_id in index.id_to_pos:
                pos = index.id_to_pos[product_id]
                return MatchResult(
                    candidates=[MatchCandidate(
                        product_id=product_id,
                        search_string=index.search_strings[pos],
                        confidence=0.99,
                        components={"source": 1.0},
                    )],
                    stage_ms=timings,
                    exact_alias_hit=True,
                )

        # --- Stage 1 ---
        t = time.perf_counter()
        candidate_ids = _trigram_candidates(conn, settings, n_name, settings.candidate_limit)
        timings["candidates"] = (time.perf_counter() - t) * 1000

    # --- Stage 2 ---
    t = time.perf_counter()
    results = _rerank(index, settings, candidate_ids, n_name, n_maker, q_feats, top_n)
    timings["rerank"] = (time.perf_counter() - t) * 1000

    return MatchResult(candidates=results, stage_ms=timings)


def match_batch(queries: Sequence[MatchQuery], *, top_n: int = 5) -> list[MatchResult]:
    """Vectorized batch match. Currently a loop -- TF-IDF transform of
    queries could be batched in a future optimization, but the per-query
    work is dominated by the DB roundtrip anyway."""
    return [match(q, top_n=top_n) for q in queries]
