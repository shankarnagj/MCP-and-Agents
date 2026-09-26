"""Deterministic tokenisation, sentence splitting and edit-distance helpers.

The tokenizer here is a plain regular expression. It is *not* Claude's
tokenizer (which is not used or reproduced); counts are therefore
"regex tokens", useful only for relative comparison.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Iterable

WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
TOKEN_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*|[^\w\s]|_", re.UNICODE)

# Abbreviations that end with a period but do not end a sentence.
_ABBREVIATIONS = {
    "e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "prof", "sr", "jr",
    "fig", "eq", "no", "vol", "al", "approx", "cf", "st", "inc", "ltd", "co",
    "u.s", "p", "pp", "sec", "ch",
}

_SENT_END_RE = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s+|$)")


def words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def strip_format_chars(text: str) -> str:
    """Remove Unicode format (Cf) characters such as zero-width spaces."""
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of sentences, splitting on terminal punctuation
    and blank lines. End offsets exclude trailing whitespace."""
    spans: list[tuple[int, int]] = []
    for para_start, para_end in paragraph_spans(text):
        start = para_start
        para = text[para_start:para_end]
        for m in _SENT_END_RE.finditer(para):
            end = para_start + m.end()
            prev_word = re.search(r"([\w.]+)\.$", text[start: para_start + m.start() + 1])
            if m.group().startswith(".") and len(m.group().rstrip("\"'”’)]")) == 1:
                if prev_word and prev_word.group(1).lower().rstrip(".") in _ABBREVIATIONS:
                    continue
                # Decimal numbers / single initials: "3.5", "J. Smith"
                if prev_word and len(prev_word.group(1)) == 1 and prev_word.group(1).isupper():
                    continue
            if text[start:end].strip():
                s = start + (len(text[start:end]) - len(text[start:end].lstrip()))
                spans.append((s, end))
            start = end
        if text[start:para_end].strip():
            s = start + (len(text[start:para_end]) - len(text[start:para_end].lstrip()))
            e = para_end - (len(text[start:para_end]) - len(text[start:para_end].rstrip()))
            spans.append((s, e))
    return spans


def sentences(text: str) -> list[str]:
    return [text[s:e] for s, e in sentence_spans(text)]


def paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    pos = 0
    for m in re.finditer(r"\n[ \t]*\n+", text):
        if text[pos:m.start()].strip():
            spans.append((pos, m.start()))
        pos = m.end()
    if text[pos:].strip():
        spans.append((pos, len(text)))
    return spans


def levenshtein(a: str, b: str) -> int:
    """Exact Levenshtein distance, O(len(a)*len(b)) time, O(min) memory."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _paired_units(a: str, b: str) -> list[tuple[str, str]] | None:
    """Pair paragraphs (then sentences) 1:1 when both texts have the same
    number of units. Deterministic transformations never add or drop
    paragraphs, so pairing avoids difflib mis-aligning repeated content."""
    pa = [a[s:e] for s, e in paragraph_spans(a)]
    pb = [b[s:e] for s, e in paragraph_spans(b)]
    if len(pa) == len(pb) and len(pa) > 1:
        return list(zip(pa, pb))
    return None


def _chunk_distance(a: str, b: str, exact_limit: int) -> int:
    if len(a) <= exact_limit and len(b) <= exact_limit:
        return levenshtein(a, b)
    ta = re.findall(r"\S+|\s+", a)
    tb = re.findall(r"\S+|\s+", b)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    total = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        ra, rb = "".join(ta[i1:i2]), "".join(tb[j1:j2])
        if len(ra) * len(rb) > 4_000_000:
            total += max(len(ra), len(rb))
        else:
            total += levenshtein(ra, rb)
    return total


def anchored_edit_distance(a: str, b: str, exact_limit: int = 1500) -> int:
    """Character edit distance between two arbitrary texts.

    Short texts get the exact Levenshtein distance. Longer texts are first
    paired paragraph-by-paragraph (when paragraph counts match), and each
    pair is aligned on whitespace-delimited chunks with difflib; exact
    Levenshtein is computed inside every changed region. The result is an
    upper bound on the global Levenshtein distance, exact whenever the
    alignment is optimal (typical for local edits). Text between paragraphs
    (blank-line runs) is compared separately.
    """
    if a == b:
        return 0
    if len(a) <= exact_limit and len(b) <= exact_limit:
        return levenshtein(a, b)
    pairs = _paired_units(a, b)
    if pairs is None:
        return _chunk_distance(a, b, exact_limit)
    total = sum(_chunk_distance(x, y, exact_limit) for x, y in pairs)
    # Separator changes (e.g. collapsed blank lines) between paragraphs.
    sep_a = [a[e1:s2] for (_, e1), (s2, _) in zip(paragraph_spans(a), paragraph_spans(a)[1:])]
    sep_b = [b[e1:s2] for (_, e1), (s2, _) in zip(paragraph_spans(b), paragraph_spans(b)[1:])]
    total += sum(levenshtein(x, y) for x, y in zip(sep_a, sep_b))
    pa, pb = paragraph_spans(a), paragraph_spans(b)
    total += levenshtein(a[:pa[0][0]], b[:pb[0][0]]) + levenshtein(a[pa[-1][1]:], b[pb[-1][1]:])
    return total


def _word_diff(a: str, b: str) -> int:
    wa, wb = words(a), words(b)
    sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")


def changed_word_count(a: str, b: str) -> int:
    """Number of word positions that differ after a word-level alignment
    (paragraph-anchored when possible)."""
    pairs = _paired_units(a, b)
    if pairs is None:
        return _word_diff(a, b)
    return sum(_word_diff(x, y) for x, y in pairs if x != y)


def _sentence_diff(a: str, b: str) -> int:
    sa = [s.strip() for s in sentences(a)]
    sb = [s.strip() for s in sentences(b)]
    sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")


def changed_sentence_count(a: str, b: str) -> int:
    pairs = _paired_units(a, b)
    if pairs is None:
        return _sentence_diff(a, b)
    return sum(_sentence_diff(x, y) for x, y in pairs if x != y)


def ngrams(seq: list[str], n: int) -> Iterable[tuple[str, ...]]:
    return (tuple(seq[i:i + n]) for i in range(len(seq) - n + 1))


def match_case(template: str, word: str) -> str:
    """Give `word` the capitalisation pattern of `template`."""
    if template.isupper() and len(template) > 1:
        return word.upper()
    if template[:1].isupper():
        return word[:1].upper() + word[1:]
    return word
