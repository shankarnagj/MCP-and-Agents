"""Baseline descriptive statistics of an input text (no transformation)."""

from __future__ import annotations

import statistics
import unicodedata
from collections import Counter

from .protect import code_blocks, split_code_comments
from .textutil import ngrams, paragraph_spans, sentences, tokens, words
from .unicode_diag import analyze_unicode


def _describe(values: list[int]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": round(statistics.fmean(values), 3),
        "median": statistics.median(values),
        "stdev": round(statistics.pstdev(values), 3),
    }


def _histogram(values: list[int], width: int = 5) -> dict[str, int]:
    hist: Counter[str] = Counter()
    for v in values:
        lo = (v // width) * width
        hist[f"{lo}-{lo + width - 1}"] += 1
    return dict(sorted(hist.items(), key=lambda kv: int(kv[0].split("-")[0])))


def split_prose_code(text: str) -> tuple[str, str, str]:
    """Return (prose, code_without_comments, comments)."""
    prose_parts, code_parts, comment_parts = [], [], []
    pos = 0
    for s, e, _lang in code_blocks(text):
        prose_parts.append(text[pos:s])
        body = text[s:e].split("\n", 1)[1] if "\n" in text[s:e] else ""
        body = body.rsplit("\n", 1)[0] if body.rstrip().endswith(("```", "~~~")) else body
        code, comments = split_code_comments(body)
        code_parts.append(code)
        comment_parts.append(comments)
        pos = e
    prose_parts.append(text[pos:])
    return "".join(prose_parts), "\n".join(code_parts), "\n".join(comment_parts)


def code_statistics(text: str) -> dict:
    prose, code, comments = split_prose_code(text)
    blocks = code_blocks(text)
    return {
        "code_blocks": len(blocks),
        "code_languages": dict(Counter(lang or "unspecified" for *_, lang in blocks)),
        "prose_tokens": len(tokens(prose)),
        "code_tokens": len(tokens(code)),
        "comment_tokens": len(tokens(comments)),
        "note": ("Tokens are regex tokens, not model tokens. Code usually offers fewer free "
                 "word choices than prose, so a token-selection watermark has less room there."),
    }


def analyze(text: str, top_n: int = 25) -> dict:
    ws = words(text)
    lw = [w.lower() for w in ws]
    sents = sentences(text)
    sent_lengths = [len(words(s)) for s in sents]
    freq = Counter(lw)
    punct = Counter(c for c in text if unicodedata.category(c).startswith("P") or c in "$+<=>^`|~")
    whitespace = Counter({" ": "space", "\t": "tab", "\n": "newline", "\r": "carriage_return",
                          " ": "nbsp"}.get(c, f"other U+{ord(c):04X}") for c in text if c.isspace())
    repeated = {}
    for n in (2, 3, 4):
        grams = Counter(ngrams(lw, n))
        repeated[f"{n}-grams"] = [{"ngram": " ".join(g), "count": c}
                                  for g, c in grams.most_common(top_n) if c >= 2]
    hapax = sum(1 for c in freq.values() if c == 1)
    # Moving-average TTR over 50-word windows is length-robust.
    window = 50
    mattr = None
    if len(lw) >= window:
        ttrs = [len(set(lw[i:i + window])) / window for i in range(0, len(lw) - window + 1)]
        mattr = round(statistics.fmean(ttrs), 4)
    return {
        "character_count": len(text),
        "token_count": len(tokens(text)),
        "token_definition": "regex tokens (words and individual punctuation marks); not a model tokenizer",
        "word_count": len(ws),
        "sentence_count": len(sents),
        "paragraph_count": len(paragraph_spans(text)),
        "unicode_categories": dict(sorted(Counter(unicodedata.category(c) for c in text).items())),
        "punctuation_distribution": dict(punct.most_common()),
        "whitespace_distribution": dict(whitespace.most_common()),
        "lexical_diversity": {
            "types": len(freq),
            "type_token_ratio": round(len(freq) / len(lw), 4) if lw else 0.0,
            "root_ttr": round(len(freq) / (len(lw) ** 0.5), 4) if lw else 0.0,
            "moving_average_ttr_50": mattr,
            "hapax_legomena": hapax,
            "hapax_ratio": round(hapax / len(freq), 4) if freq else 0.0,
        },
        "repeated_ngrams": repeated,
        "word_frequency_top": [{"word": w, "count": c} for w, c in freq.most_common(top_n)],
        "sentence_length_words": _describe(sent_lengths),
        "sentence_length_histogram": _histogram(sent_lengths),
        "code": code_statistics(text),
        "unicode_summary": {k: v for k, v in analyze_unicode(text).items()
                            if k in ("counts", "total_suspicious")},
    }
