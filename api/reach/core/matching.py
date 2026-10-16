"""Entity name matching and keyword understanding, used as the fallback when Claude is unavailable
and as the resolver for whatever Claude returns. Deterministic, no I/O.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

Lang = Literal["sw", "en"]
Intent = Literal["report", "query", "help", "other"]

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")
STOP_WORDS = frozenset(
    {"the", "is", "a", "an", "at", "of", "in", "on", "cha", "ya", "wa", "la", "na", "ni", "kwa"}
)
SWAHILI_MARKERS = (
    "kisima",
    "maji",
    "imeharibika",
    "inafanya",
    "kazi",
    "haifanyi",
    "hakuna",
    "karibu",
    "zahanati",
    "imefungwa",
    "wapi",
    "iko",
    "haina",
    "kavu",
    "mbovu",
    "asante",
    "habari",
    "msaada",
    "kituo",
    "dawa",
    "kijiji",
    "nzuri",
    "sawa",
    "ndiyo",
    "hapana",
    "chakula",
    "lishe",
)
HELP_WORDS = ("help", "msaada", "how do i", "what can", "nifanye nini", "jinsi")
QUESTION_STARTS = (
    "is ",
    "are ",
    "does ",
    "do ",
    "where",
    "which",
    "what",
    "how",
    "je ",
    "wapi",
    "kuna",
    "ni wapi",
    "iko wapi",
)
QUESTION_WORDS = (
    "where",
    "wapi",
    "which",
    "gani",
    "nearest",
    "karibu",
    "is there",
    "kuna",
    "?",
    "status",
    "hali",
)


@dataclass(frozen=True)
class NameCandidate:
    id: str
    name: str
    aliases: tuple[str, ...] = ()


def normalize(text: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return _SPACES.sub(" ", _PUNCT.sub(" ", stripped.lower())).strip()


def tokens(text: str) -> list[str]:
    return [t for t in normalize(text).split() if t not in STOP_WORDS]


def _fuzzy_equal(a: str, b: str) -> bool:
    """Cheap tolerance for speech-to-text spelling drift: same 4-letter prefix, similar length."""
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    return a[:4] == b[:4] and abs(len(a) - len(b)) <= 2


def _idf_table(candidates: Iterable[NameCandidate]) -> dict[str, float]:
    cands = list(candidates)
    doc_freq: Counter[str] = Counter()
    for cand in cands:
        seen: set[str] = set()
        for label in (cand.name, *cand.aliases):
            seen.update(tokens(label))
        doc_freq.update(seen)
    n = max(1, len(cands))
    return {tok: 1.0 + math.log((n + 1) / (df + 1)) for tok, df in doc_freq.items()}


def score_candidate(text: str, candidate: NameCandidate, idf: Mapping[str, float] | None = None) -> float:
    """1.0 for an exact (normalized) label inside the text, otherwise IDF-weighted token coverage × 0.9."""
    text_norm = normalize(text)
    text_toks = set(tokens(text))
    best = 0.0
    for label in (candidate.name, *candidate.aliases):
        label_norm = normalize(label)
        if not label_norm:
            continue
        if f" {label_norm} " in f" {text_norm} ":
            return 1.0
        label_toks = tokens(label)
        if not label_toks:
            continue
        weights = [idf.get(t, 1.0) if idf else 1.0 for t in label_toks]
        hits = [
            w for t, w in zip(label_toks, weights, strict=True) if any(_fuzzy_equal(t, x) for x in text_toks)
        ]
        if hits:
            best = max(best, 0.9 * sum(hits) / sum(weights))
    return round(best, 3)


def best_matches(text: str, candidates: Iterable[NameCandidate], limit: int = 3) -> list[tuple[str, float]]:
    cands = list(candidates)
    idf = _idf_table(cands)
    scored = [(c.id, score_candidate(text, c, idf)) for c in cands]
    scored = [s for s in scored if s[1] > 0.0]
    scored.sort(key=lambda s: (-s[1], s[0]))
    return scored[:limit]


def detect_status(text: str, keywords: Mapping[str, Iterable[str]]) -> str | None:
    """Longest matching keyword wins so 'haina maji' (empty) beats a generic 'maji'."""
    text_norm = f" {normalize(text)} "
    best: tuple[int, str] | None = None
    for status, words in keywords.items():
        for word in words:
            w = normalize(word)
            if w and f" {w} " in text_norm and (best is None or len(w) > best[0]):
                best = (len(w), status)
    return best[1] if best else None


def detect_lang(text: str) -> Lang:
    norm = f" {normalize(text)} "
    return "sw" if any(f" {m} " in norm for m in SWAHILI_MARKERS) else "en"


def is_question(text: str) -> bool:
    """Questions never record a status, even when they contain a status word ("is it working?")."""
    stripped = text.strip()
    norm = normalize(stripped)
    return stripped.endswith("?") or any(norm.startswith(q) for q in QUESTION_STARTS) or " wapi" in f" {norm}"


def detect_intent(text: str, has_status: bool, has_entity: bool) -> Intent:
    norm = normalize(text)
    if any(h in norm for h in HELP_WORDS) and not has_status:
        return "help"
    if has_status and not is_question(text):
        return "report"
    if has_entity or any(q in f"{norm} {text}" for q in QUESTION_WORDS):
        return "query"
    return "other"
