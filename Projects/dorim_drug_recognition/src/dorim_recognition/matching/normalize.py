"""Text normalization utilities for drug names and manufacturers.

Goal: collapse spelling/formatting variation while preserving semantically
important tokens (dosages, counts, drug names).

Rules (in order):
1. Lowercase.
2. Replace Latin lookalikes that often appear in Cyrillic text and vice versa.
3. Strip punctuation except dot in numbers (e.g. "2.5"), comma in numbers,
   percent sign, and the # sign for counts.
4. Normalize unit spellings: "мг" / "mg", "мл" / "ml", "г" / "g", "%".
5. Normalize count markers: "№10", "#10", "x10", "по 10", "n10" -> "№10".
6. Collapse whitespace.

We expose two helpers:
- normalize_text(s) — for fuzzy/TF-IDF/trigram matching (very aggressive).
- extract_dosage_features(s) — returns dict of structured numeric features
  (dose values, count, volume) for the dosage-score component.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_UNIT_SYNONYMS = [
    # (pattern, canonical) — apply on lowercase
    (re.compile(r"\bмиллиграмм(а|ов)?\b"), "мг"),
    (re.compile(r"\bмилиграмм(а|ов)?\b"), "мг"),
    (re.compile(r"\bmg\b"), "мг"),
    (re.compile(r"\bмиллилитр(а|ов)?\b"), "мл"),
    (re.compile(r"\bml\b"), "мл"),
    (re.compile(r"\bгр(амм(а|ов)?)?\b"), "г"),
    (re.compile(r"\bgr?\b"), "г"),
    (re.compile(r"\bмеждународн\w+\sед\w+\b"), "ме"),
    (re.compile(r"\biu\b"), "ме"),
]


_COUNT_PATTERNS = [
    re.compile(r"#\s*(\d+)"),
    re.compile(r"№\s*(\d+)"),
    re.compile(r"\bn\s*(\d+)\b", re.IGNORECASE),
    re.compile(r"\bпо\s+(\d+)\b"),
    re.compile(r"(\d+)\s*шт\b"),
]


# Tokens that add noise but no signal (filler words, registration marks).
_NOISE = re.compile(r"[®©™«»\"'`´‘’“”]")
# Anything that is not a letter (latin/cyrillic), digit, dot/comma in numbers,
# percent, slash, dash, or count sign -> space.
_PUNCT_TO_SPACE = re.compile(r"[^\w%.,/\-№]+", re.UNICODE)
_MULTI_WS = re.compile(r"\s+")
# Internal helper: keep "2.5" but turn ". " / " ." into space.
_DANGLING_DOT = re.compile(r"(?<!\d)\.(?!\d)")
_DANGLING_COMMA = re.compile(r"(?<!\d),(?!\d)")
# Replace common form abbreviations to canonical short form for better trigram hits.
_FORM_SYNONYMS = [
    # Order matters: longer/more-specific forms first.
    (re.compile(r"\bтаблетк[аиыу]?\b"), "табл"),
    (re.compile(r"\bтабл\.?\b"), "табл"),
    (re.compile(r"\bтаб\.?\b"), "табл"),  # "Парацетамол таб 500мг" -- canonicalize to "табл".
    (re.compile(r"\bкапсул[аыуы]?\b"), "капс"),
    (re.compile(r"\bкапс\.?\b"), "капс"),
    (re.compile(r"\bраствор[а-я]*\b"), "р-р"),
    (re.compile(r"\bпорошок\b"), "пор"),
    (re.compile(r"\bсироп[а-я]*\b"), "сироп"),
    (re.compile(r"\bампул[аыуы]?\b"), "амп"),
    (re.compile(r"\bфлакон[а-я]*\b"), "фл"),
    (re.compile(r"\bблистер[а-я]*\b"), "бл"),
    (re.compile(r"\bсаше\b"), "саше"),
    (re.compile(r"\bкрем[а-я]*\b"), "крем"),
    (re.compile(r"\bмаз[а-я]*\b"), "мазь"),
    (re.compile(r"\bгел[а-я]*\b"), "гель"),
    (re.compile(r"\bспрей[а-я]*\b"), "спрей"),
    (re.compile(r"\bдля\s+ин(ъ|ь)екц[а-я]*\b"), "д/ин"),
    (re.compile(r"\bд/ин\.?\b"), "д/ин"),
]

# Insert a space between a digit and a unit so "500мг" and "500 мг" normalize
# to the same form. Apply BEFORE _UNIT_SYNONYMS so it works on raw input.
_DIGIT_UNIT_SPLIT = re.compile(
    r"(\d)\s*(мг|мл|г|ме|мкг|кг|л|%)\b",
)


def normalize_text(s: str | None) -> str:
    """Aggressively normalize a string for matching/indexing.

    Idempotent: ``normalize_text(normalize_text(x)) == normalize_text(x)``.
    """
    if not s:
        return ""
    s = s.lower()
    s = _NOISE.sub(" ", s)

    # Always separate digits from units before further processing.
    s = _DIGIT_UNIT_SPLIT.sub(r"\1 \2", s)

    # Unit/form synonyms applied on text with words still separated by spaces.
    for pat, repl in _UNIT_SYNONYMS:
        s = pat.sub(repl, s)
    for pat, repl in _FORM_SYNONYMS:
        s = pat.sub(repl, s)

    # Counts -> "№N"
    for pat in _COUNT_PATTERNS:
        s = pat.sub(r"№\1", s)

    s = _PUNCT_TO_SPACE.sub(" ", s)
    s = _DANGLING_DOT.sub(" ", s)
    s = _DANGLING_COMMA.sub(" ", s)
    s = _MULTI_WS.sub(" ", s).strip()
    return s


def normalize_maker(s: str | None) -> str:
    """Normalize a manufacturer string. Same as text, but extra tolerant
    (manufacturer field is the noisiest)."""
    if not s:
        return ""
    s = normalize_text(s)
    # drop common country tails / separators like "-узб", "/индия"
    s = re.sub(r"[/\\-]+", " ", s)
    s = _MULTI_WS.sub(" ", s).strip()
    return s


# --- structured dosage extraction ----------------------------------------------


@dataclass(frozen=True)
class DosageFeatures:
    """Numeric features extracted from a drug string.

    Each field is a *set* because multi-component drugs may carry several
    dosages (e.g. "192/50/25 мг"). Sets make comparison order-insensitive.
    """

    mg: frozenset[float]
    ml: frozenset[float]
    g: frozenset[float]
    me: frozenset[float]  # МЕ / IU
    percent: frozenset[float]
    count: int | None  # №N
    volume_ml: float | None  # explicit volume (e.g. "2 мл")


_NUM = r"\d+(?:[.,]\d+)?"


def _floats(rx: str, s: str) -> frozenset[float]:
    out: set[float] = set()
    for m in re.finditer(rx, s):
        try:
            out.add(float(m.group(1).replace(",", ".")))
        except ValueError:  # pragma: no cover - defensive
            continue
    return frozenset(out)


def extract_dosage_features(normalized: str) -> DosageFeatures:
    """Extract structured numeric features from an already-normalized string."""
    mg = _floats(rf"({_NUM})\s*мг", normalized)
    ml = _floats(rf"({_NUM})\s*мл", normalized)
    g_ = _floats(rf"({_NUM})\s*г\b(?!/)", normalized)
    me = _floats(rf"({_NUM})\s*ме\b", normalized)
    percent = _floats(rf"({_NUM})\s*%", normalized)

    count: int | None = None
    m = re.search(r"№(\d+)", normalized)
    if m:
        try:
            count = int(m.group(1))
        except ValueError:  # pragma: no cover
            count = None

    # Also catch slashed multi-dose: "192/50/25 мг"
    multi = re.search(rf"({_NUM}(?:/{_NUM})+)\s*мг", normalized)
    if multi:
        extra: set[float] = set()
        for part in multi.group(1).split("/"):
            try:
                extra.add(float(part.replace(",", ".")))
            except ValueError:  # pragma: no cover
                pass
        mg = mg | frozenset(extra)

    return DosageFeatures(
        mg=mg, ml=ml, g=g_, me=me, percent=percent, count=count, volume_ml=None,
    )


def _g_as_mg(g: frozenset[float]) -> frozenset[float]:
    """Convert small gram values (likely active substance doses) to mg.

    >= 5 g is almost always packaging weight (cream tubes, powders) so we
    leave it alone -- it lives in the ``g`` dimension and is compared there.
    """
    return frozenset(round(v * 1000.0, 4) for v in g if v < 5.0)


def dosage_similarity(a: DosageFeatures, b: DosageFeatures) -> float:
    """Return [0, 1] similarity between two dosage feature sets.

    Strategy:
    - For each non-empty dimension compute Jaccard overlap.
    - mg and g (when g < 5 g, i.e. drug dose not packaging) are treated as
      the same dimension after unit conversion, so "0,05 г" matches "50 мг".
    - Count compared exactly (same/different).
    - Both sides empty in every dimension -> 0.5 (neutral).
    """
    parts: list[float] = []

    # Combined mass-of-active-substance dimension (mg + small-g promoted).
    a_mass = a.mg | _g_as_mg(a.g)
    b_mass = b.mg | _g_as_mg(b.g)
    if a_mass or b_mass:
        if not a_mass or not b_mass:
            parts.append(0.0)
        else:
            inter = len(a_mass & b_mass)
            union = len(a_mass | b_mass)
            parts.append(inter / union if union else 0.0)

    # Large grams (packaging) -- compared separately.
    a_big_g = frozenset(v for v in a.g if v >= 5.0)
    b_big_g = frozenset(v for v in b.g if v >= 5.0)
    if a_big_g or b_big_g:
        if not a_big_g or not b_big_g:
            parts.append(0.0)
        else:
            parts.append(len(a_big_g & b_big_g) / len(a_big_g | b_big_g))

    for x, y in [(a.ml, b.ml), (a.me, b.me), (a.percent, b.percent)]:
        if not x and not y:
            continue
        if not x or not y:
            parts.append(0.0)
            continue
        parts.append(len(x & y) / len(x | y))

    if a.count is not None and b.count is not None:
        parts.append(1.0 if a.count == b.count else 0.0)

    if not parts:
        return 0.5
    return sum(parts) / len(parts)
