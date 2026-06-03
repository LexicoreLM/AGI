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


@dataclass
class VerifyResult:
    """Result of verifying that a (name, maker) → drug_id binding is correct.

    See ``_verdict_for`` for the authoritative list of ``verdict`` values.
    """

    drug_id: int
    product_search_string: str | None  # None iff drug_id is not in catalog
    confidence: float                  # 0..1, weighted hybrid score
    components: dict[str, float]       # fuzzy / tfidf / maker / dosage
    verdict: str
    alias_match: bool                  # exact-alias short-circuit returned drug_id
    alias_conflict_with: int | None    # existing alias points to a different drug
    engine_top_pick: MatchCandidate | None  # what match() would pick instead
    stage_ms: dict[str, float]

    @property
    def engine_agrees(self) -> bool:
        """True iff the engine's own top pick matches ``drug_id``."""
        return self.engine_top_pick is not None and self.engine_top_pick.product_id == self.drug_id


# -----------------------------------------------------------------------------
# Index cache: catalog + TF-IDF
# -----------------------------------------------------------------------------

@dataclass
class _CatalogIndex:
    """All in-memory artifacts needed for matching."""

    product_ids: np.ndarray  # shape (N,)
    search_strings: list[str]
    normalized: list[str]
    makers_canonical: list[str]  # parsed maker tokens only (or empty)
    countries: list[str]
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
                f"SELECT id, search_string, normalized, maker_canonical, country, "
                f"mg_values, ml_values, g_values, me_values, percent_values, count_n "
                f"FROM {settings.engine_schema}.products ORDER BY id"
            )
            rows = cur.fetchall()

    product_ids = np.array([r["id"] for r in rows], dtype=np.int64)
    search_strings = [r["search_string"] for r in rows]
    normalized = [r["normalized"] for r in rows]
    makers_canonical = [r["maker_canonical"] for r in rows]
    countries = [r["country"] for r in rows]
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
        makers_canonical=makers_canonical,
        countries=countries,
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

# Below this raw partial_ratio the maker is treated as "absent" in the product.
# Empirically 0.5 (i.e. 50%) on noisy cyrillic data filters incidental matches
# while keeping legitimate transliteration / abbreviation cases.
_MAKER_FLOOR = 0.5

# Country names that frequently appear inside maker_name input. We strip them
# so "ИНДИЯ, Dr.Reddys lab" -> "dr reddys lab" rather than "dr reddys lab индия"
# (the country is checked separately via the country bonus path).
_COUNTRY_STOP_TOKENS = frozenset({
    "индия", "россия", "узбекистан", "украина", "беларусь", "германия", "франция",
    "италия", "польша", "сша", "китай", "корея", "турция", "венгрия", "словения",
    "испания", "швейцария", "болгария", "вьетнам", "пакистан", "казахстан",
    "грузия", "армения", "молдова", "австрия", "нидерланды", "великобритания",
    "ирландия", "греция", "португалия",
})


def _maker_score(
    query_maker: str,
    product_maker: str,
    product_country: str = "",
    product_norm: str = "",
) -> float:
    """Strict manufacturer scoring using the catalog's parsed maker field.

    Compares the input manufacturer string against the catalog row's
    ``maker_canonical`` (extracted by ``parse_search_string``). This avoids
    the previous bug where country tokens inside the FULL product string
    inflated the score for the wrong product.

    Strategy:
      - No query maker -> 0.5 (neutral, no signal).
      - Strip country tokens from the query (e.g. "ИНДИЯ, Dr.Reddys lab"
        becomes "dr reddys lab") -- country is matched separately via the
        country bonus.
      - If catalog has a parsed maker: use ``token_set_ratio`` (handles
        word reorder) + ``partial_ratio`` (handles substring), take max.
        Pass through a steep curve to suppress incidental matches.
      - Country bonus: if the country token appears in the query maker
        string AND the maker score is low, lift the floor to 0.4 so a
        country-only signal isn't completely lost.
      - Fall back to comparing against ``product_norm`` if the catalog has
        no parsed maker (~4.5% of rows).
    """
    if not query_maker:
        return 0.5

    # Strip out country tokens from the query -- they're scored separately.
    q_tokens = [t for t in query_maker.split() if t not in _COUNTRY_STOP_TOKENS]
    q_core = " ".join(q_tokens)
    if not q_core:
        # query was ONLY a country -- weak signal, see if country matches.
        if product_country and any(t in product_country for t in query_maker.split()):
            return 0.5
        return 0.2

    if product_maker:
        target = product_maker
        ts = fuzz.token_set_ratio(q_core, target) / 100.0
        pr = fuzz.partial_ratio(q_core, target) / 100.0
        raw = max(ts, pr)
    else:
        # Fallback to legacy "match against full product" behaviour.
        raw = fuzz.partial_ratio(q_core, product_norm) / 100.0

    steep = max(0.0, min(1.0, (raw - _MAKER_FLOOR) / (1.0 - _MAKER_FLOOR)))

    # Token-membership floor.
    q_long = [t for t in q_core.split() if len(t) >= 4]
    if q_long and product_maker:
        hits = sum(1 for t in q_long if t in product_maker)
        if hits:
            steep = max(steep, 0.6 + 0.4 * (hits / len(q_long)))

    # Country bonus: even if maker doesn't match, partial credit if the user
    # at least named the right country -- distinguishes regional variants.
    if product_country and product_country in query_maker:
        steep = max(steep, 0.4)

    return float(steep)

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
    fuzzy_scores = np.empty(positions.size, dtype=np.float32)
    maker_scores = np.empty(positions.size, dtype=np.float32)
    dose_scores = np.empty(positions.size, dtype=np.float32)
    for i, p in enumerate(positions):
        product_norm = index.normalized[p]
        product_maker = index.makers_canonical[p]
        product_country = index.countries[p]
        fuzzy_scores[i] = fuzz.token_set_ratio(n_name, product_norm) / 100.0
        maker_scores[i] = _maker_score(n_maker, product_maker, product_country, product_norm)
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


# -----------------------------------------------------------------------------
# Verify: score a proposed (name, maker) -> drug_id binding
# -----------------------------------------------------------------------------

def _score_pair(
    index: _CatalogIndex,
    settings: Settings,
    pos: int,
    n_name: str,
    n_maker: str,
    q_feats: DosageFeatures,
) -> tuple[float, dict[str, float]]:
    """Compute the weighted hybrid score for a single (query, product) pair.

    Returns ``(final_score, components_dict)``. Shared between ``_rerank``
    (vectorized) and ``verify_binding`` (one-shot). Keeping it here means a
    weight change in ``Settings`` automatically applies to both code paths.
    """
    product_norm = index.normalized[pos]
    fuzzy = fuzz.token_set_ratio(n_name, product_norm) / 100.0
    maker = _maker_score(
        n_maker, index.makers_canonical[pos], index.countries[pos], product_norm,
    )
    dose = dosage_similarity(q_feats, index.dose_features[pos])

    query_vec = index.vectorizer.transform([n_name])
    query_vec = l2_normalize(query_vec, norm="l2", copy=False)
    product_vec = index.tfidf_matrix[pos : pos + 1]
    tfidf = float((product_vec @ query_vec.T).toarray().ravel()[0])

    final = (
        settings.w_fuzzy * fuzzy
        + settings.w_tfidf * tfidf
        + settings.w_maker * maker
        + settings.w_dosage * dose
    )
    return float(final), {
        "fuzzy": round(fuzzy, 4),
        "tfidf": round(tfidf, 4),
        "maker": round(maker, 4),
        "dosage": round(dose, 4),
    }


# Verdict catalog: single source of truth shared by ``_verdict_for`` (which
# emits keys) and API consumers (which need human-readable labels). Keys must
# stay in sync with the branches in ``_verdict_for``.
VERDICT_LABELS: dict[str, str] = {
    "exact_alias":         "точное совпадение с подтверждённой привязкой",
    "conflict_with_alias": "конфликт: эта же пара уже привязана к другому товару",
    "highly_likely":       "высокая вероятность правильной привязки",
    "likely":              "скорее правильная привязка",
    "plausible":           "правдоподобная, требует проверки",
    "unlikely":            "сомнительная привязка",
    "unknown_drug":        "товар не найден в каталоге",
    "empty_query":         "пустое название после нормализации",
}


def _verdict_for(
    confidence: float,
    alias_match: bool,
    alias_conflict: bool,
) -> str:
    """Map (confidence, alias signals) to a verdict key from ``VERDICT_LABELS``.

    Note: ``unknown_drug`` and ``empty_query`` are emitted directly by
    ``verify_binding`` before this function is reached.
    """
    if alias_match:
        return "exact_alias"
    if alias_conflict:
        return "conflict_with_alias"
    if confidence >= 0.85:
        return "highly_likely"
    if confidence >= 0.65:
        return "likely"
    if confidence >= 0.50:
        return "plausible"
    return "unlikely"


def _empty_verify_result(drug_id: int, verdict: str) -> VerifyResult:
    """Build a VerifyResult for short-circuit cases (unknown drug, empty query)."""
    return VerifyResult(
        drug_id=drug_id,
        product_search_string=None,
        confidence=0.0,
        components={},
        verdict=verdict,
        alias_match=False,
        alias_conflict_with=None,
        engine_top_pick=None,
        stage_ms={},
    )


def verify_binding(
    query: MatchQuery,
    drug_id: int,
    *,
    include_top_pick: bool = True,
) -> VerifyResult:
    """Score the proposed binding (query → drug_id).

    Returns confidence in [0, 1] for the *specific* binding plus, for
    context, what the engine would have picked on its own. Useful for QC
    of historical mappings: feed (contractor_name, contractor_maker,
    our_drug_id) and the response tells you how plausible that mapping is.

    See ``VERDICT_LABELS`` for the full set of verdict values.
    """
    settings = get_settings()
    index = get_index()
    timings: dict[str, float] = {}

    n_name = normalize_text(query.name)
    n_maker = normalize_maker(query.maker_name) if query.maker_name else ""

    if not n_name:
        return _empty_verify_result(drug_id, "empty_query")
    pos = index.id_to_pos.get(drug_id)
    if pos is None:
        return _empty_verify_result(drug_id, "unknown_drug")

    # --- Per-pair score ---
    t = time.perf_counter()
    q_feats = extract_dosage_features(n_name)
    confidence, components = _score_pair(index, settings, pos, n_name, n_maker, q_feats)
    timings["score"] = (time.perf_counter() - t) * 1000

    # --- Alias short-circuit lookup ---
    t = time.perf_counter()
    with raw_connection(autocommit=True) as conn:
        sc_product_id = _alias_short_circuit(conn, settings, n_name, n_maker)
    timings["alias"] = (time.perf_counter() - t) * 1000

    alias_match = sc_product_id == drug_id
    alias_conflict_with = sc_product_id if sc_product_id not in (None, drug_id) else None
    if alias_match:
        # Promote confidence to the exact-alias floor (same as match() does).
        confidence = max(confidence, 0.99)

    # --- Engine's own top pick (independent run, no shortcircuit so we get
    #     a fair fuzzy score for comparison even when the alias would override).
    engine_top: MatchCandidate | None = None
    if include_top_pick:
        t = time.perf_counter()
        top_res = match(query, top_n=1, use_alias_shortcircuit=False)
        timings["top_pick"] = (time.perf_counter() - t) * 1000
        if top_res.candidates:
            engine_top = top_res.candidates[0]

    return VerifyResult(
        drug_id=drug_id,
        product_search_string=index.search_strings[pos],
        confidence=round(confidence, 4),
        components=components,
        verdict=_verdict_for(confidence, alias_match, bool(alias_conflict_with)),
        alias_match=alias_match,
        alias_conflict_with=alias_conflict_with,
        engine_top_pick=engine_top,
        stage_ms={k: round(v, 2) for k, v in timings.items()},
    )
