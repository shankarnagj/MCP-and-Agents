"""Unicode diagnostic: hidden/invisible/confusable characters.

IMPORTANT: none of the characters reported here is Claude's text watermark.
Anthropic states that its text watermark adds nothing to the text and uses no
hidden characters; it is statistical, living in which words are chosen. This
diagnostic exists as a *control*: it shows what is (or is not) present at the
character level, so that character-level cleanup can be tested separately.
"""

from __future__ import annotations

import unicodedata
from collections import Counter

ZERO_WIDTH = {
    0x200B: "ZERO WIDTH SPACE",
    0x200C: "ZERO WIDTH NON-JOINER",
    0x200D: "ZERO WIDTH JOINER",
    0x2060: "WORD JOINER",
    0xFEFF: "ZERO WIDTH NO-BREAK SPACE / BOM",
    0x180E: "MONGOLIAN VOWEL SEPARATOR",
    0x00AD: "SOFT HYPHEN",
    0x2061: "FUNCTION APPLICATION", 0x2062: "INVISIBLE TIMES",
    0x2063: "INVISIBLE SEPARATOR", 0x2064: "INVISIBLE PLUS",
}
BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A)) | {0x200E, 0x200F, 0x061C}
UNUSUAL_WS = {0x00A0, 0x1680, 0x202F, 0x205F, 0x3000, 0x0085, 0x000B, 0x000C, 0x2028, 0x2029} | set(range(0x2000, 0x200B))

INVISIBLE_CATEGORIES = {"zero_width", "bidi_control", "tag_character", "variation_selector", "other_format"}

# Small confusables table: non-Latin letters that render like Latin ones.
HOMOGLYPHS = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
    "у": "y", "і": "i", "ј": "j", "һ": "h", "ԁ": "d", "ԛ": "q",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
    "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X", "І": "I",
    "ο": "o", "α": "a", "ν": "v", "ρ": "p", "Α": "A", "Β": "B",
    "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M",
    "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "ａ": "a", "ｅ": "e", "ｏ": "o", "ⅼ": "l", "ⅰ": "i",
}


def classify_char(ch: str) -> str | None:
    cp = ord(ch)
    if cp in ZERO_WIDTH:
        return "zero_width"
    if cp in BIDI:
        return "bidi_control"
    if 0xE0000 <= cp <= 0xE007F:
        return "tag_character"
    if 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF or 0x180B <= cp <= 0x180D:
        return "variation_selector"
    if cp in UNUSUAL_WS:
        return "unusual_whitespace"
    if ch in HOMOGLYPHS:
        return "homoglyph"
    if unicodedata.category(ch) == "Cf":
        return "other_format"
    return None


def _line_col(text: str, pos: int) -> tuple[int, int]:
    line = text.count("\n", 0, pos) + 1
    col = pos - (text.rfind("\n", 0, pos) + 1) + 1
    return line, col


def analyze_unicode(text: str, max_findings: int = 500) -> dict:
    findings = []
    counts: Counter[str] = Counter()
    for i, ch in enumerate(text):
        kind = classify_char(ch)
        if kind is None:
            continue
        counts[kind] += 1
        if len(findings) < max_findings:
            line, col = _line_col(text, i)
            entry = {
                "position": i, "line": line, "column": col, "kind": kind,
                "codepoint": f"U+{ord(ch):04X}", "name": unicodedata.name(ch, ZERO_WIDTH.get(ord(ch), "UNKNOWN")),
            }
            if kind == "homoglyph":
                entry["looks_like"] = HOMOGLYPHS[ch]
            findings.append(entry)
    categories = Counter(unicodedata.category(c) for c in text)
    scripts = Counter()
    for c in text:
        if c.isalpha():
            scripts[unicodedata.name(c, "UNKNOWN").split(" ")[0]] += 1
    return {
        "label": "Unicode diagnostic (character level)",
        "disclaimer": ("Characters reported here are NOT the Claude statistical watermark. Anthropic "
                       "describes that watermark as statistical (word-choice based) with no hidden "
                       "characters added. Removing these characters is a Unicode normalization "
                       "experiment, not watermark removal."),
        "length": len(text),
        "counts": dict(sorted(counts.items())),
        "total_suspicious": sum(counts.values()),
        "findings": findings,
        "findings_truncated": sum(counts.values()) > len(findings),
        "unicode_categories": dict(sorted(categories.items())),
        "letter_scripts": dict(scripts.most_common()),
        "normalization_forms_stable": {
            form: unicodedata.normalize(form, text) == text for form in ("NFC", "NFKC", "NFD", "NFKD")
        },
    }
