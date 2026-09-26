"""Classical lexical/structural similarity metrics.

These metrics do NOT establish semantic equivalence. No semantic model is
used. They are reported as "lexical/structural similarity"; semantic
equivalence requires human evaluation.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .protect import ProtectionConfig, code_blocks, find_protected
from .textutil import sentences, words

_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with", "at", "by",
    "from", "is", "are", "was", "were", "be", "been", "it", "this", "that", "as", "not",
}


def _cosine(a: Counter, b: Counter) -> float:
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 and nb == 0:
        return 1.0
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def word_overlap(a: str, b: str) -> dict:
    wa, wb = Counter(w.lower() for w in words(a)), Counter(w.lower() for w in words(b))
    sa, sb = set(wa), set(wb)
    jacc = len(sa & sb) / len(sa | sb) if sa | sb else 1.0
    inter = sum((wa & wb).values())
    total = max(sum(wa.values()), sum(wb.values()))
    return {"jaccard": round(jacc, 4), "multiset_overlap": round(inter / total, 4) if total else 1.0}


def tfidf_cosine(a: str, b: str) -> float:
    """TF-IDF cosine between two texts. IDF is estimated over the pooled
    sentences of both texts (a local, self-contained corpus)."""
    docs = [set(w.lower() for w in words(s)) for s in sentences(a) + sentences(b)]
    n = max(1, len(docs))
    df: Counter[str] = Counter()
    for d in docs:
        df.update(d)

    def vec(t: str) -> Counter:
        tf = Counter(w.lower() for w in words(t))
        return Counter({w: c * (math.log((1 + n) / (1 + df[w])) + 1.0) for w, c in tf.items()})

    return round(_cosine(vec(a), vec(b)), 4)


def char_ngram_similarity(a: str, b: str, n: int = 3) -> float:
    def grams(t: str) -> Counter:
        t = re.sub(r"\s+", " ", t.lower())
        return Counter(t[i:i + n] for i in range(len(t) - n + 1))

    return round(_cosine(grams(a), grams(b)), 4)


def sentence_length_difference(a: str, b: str) -> dict:
    la = [len(words(s)) for s in sentences(a)]
    lb = [len(words(s)) for s in sentences(b)]
    mean = lambda v: sum(v) / len(v) if v else 0.0  # noqa: E731
    paired = [abs(x - y) for x, y in zip(la, lb)]
    return {
        "sentence_count_before": len(la), "sentence_count_after": len(lb),
        "mean_length_before": round(mean(la), 3), "mean_length_after": round(mean(lb), 3),
        "mean_abs_paired_difference": round(mean(paired), 3),
    }


_ENTITY_RE = re.compile(r"(?<![.!?]\s)(?<!^)\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+|[A-Z]{2,}[A-Za-z0-9]*|[A-Z][a-z]+[A-Z]\w*)\b", re.M)


def _preservation(items_a: list[str], b_text: str, items_b: list[str] | None = None) -> dict:
    if not items_a:
        return {"count": 0, "preserved": 0, "ratio": None}
    if items_b is not None:
        cb = Counter(items_b)
        preserved = sum(min(c, cb[k]) for k, c in Counter(items_a).items())
    else:
        preserved = sum(1 for it in items_a if it in b_text)
    return {"count": len(items_a), "preserved": preserved, "ratio": round(preserved / len(items_a), 4)}


def _kind_items(text: str, kinds: set[str]) -> list[str]:
    return [text[s.start:s.end] for s in find_protected(text, ProtectionConfig()) if s.kind in kinds]


def compare(a: str, b: str) -> dict:
    ents_a = _ENTITY_RE.findall(a)
    code_a = [a[s:e] for s, e, _ in code_blocks(a)]
    code_b = [b[s:e] for s, e, _ in code_blocks(b)]
    metrics = {
        "label": "lexical/structural similarity (not semantic equivalence)",
        "identical": a == b,
        "word_overlap": word_overlap(a, b),
        "tfidf_cosine": tfidf_cosine(a, b),
        "char_3gram_cosine": char_ngram_similarity(a, b, 3),
        "sentence_length": sentence_length_difference(a, b),
        "named_entity_strings": _preservation(ents_a, b),
        "numbers": _preservation(_kind_items(a, {"number", "date"}), b, _kind_items(b, {"number", "date"})),
        "urls": _preservation(_kind_items(a, {"url", "email", "markdown_link"}), b,
                              _kind_items(b, {"url", "email", "markdown_link"})),
        "code_blocks": _preservation(code_a, b, code_b),
    }
    metrics["preservation_score"] = preservation_score(metrics)
    return metrics


def preservation_score(m: dict) -> float:
    """Weighted mean of similarity components (0..1). Components with no
    items (ratio None) are dropped and weights renormalised."""
    parts = [
        (0.35, m["tfidf_cosine"]),
        (0.25, m["char_3gram_cosine"]),
        (0.10, m["named_entity_strings"]["ratio"]),
        (0.10, m["numbers"]["ratio"]),
        (0.10, m["urls"]["ratio"]),
        (0.10, m["code_blocks"]["ratio"]),
    ]
    parts = [(w, v) for w, v in parts if v is not None]
    total = sum(w for w, _ in parts)
    return round(sum(w * v for w, v in parts) / total, 4)
