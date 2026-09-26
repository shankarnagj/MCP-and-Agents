"""Local keyed detector for the synthetic *testbed* watermark.

THIS IS NOT CLAUDE'S DETECTOR. It does not use, recover or approximate
Anthropic's key, and it cannot detect Claude's watermark. It implements a
generic, publicly documented keyed hypothesis test (a "green-list" z-test in
the style of Kirchenbauer et al., 2023) over *word* tokens, with a key that
YOU choose. It is meaningful only for text marked with the same key by
``claude_mark_research.toy_watermark`` - a deterministic, dictionary-based
lexical watermark used as a controlled stand-in for studying how
transformations disturb a token-choice signal.

Test: each scored (previous word, word) pair is "green" if
HMAC-SHA256(key, prev || word) maps below ``gamma``. Under H0 (text not
marked with this key) greens ~ Binomial(T, gamma). z = (G - gamma*T) /
sqrt(T*gamma*(1-gamma)); one-sided p-value from the normal tail. Repeated
(context, word) pairs are counted once.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import unicodedata

from ..protect import code_blocks
from ..resources import load_substitutions
from ..textutil import strip_format_chars, words
from .base import DetectionResult, WatermarkDetector

SCOPES = ("all", "lexical_slots")


def green_value(key: bytes, context: str, token: str) -> float:
    digest = hmac.new(key, f"{context}\x1f{token}".encode("utf-8"), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def slot_vocabulary() -> set[str]:
    d = load_substitutions(tiers=["conservative", "extended"])
    vocab = set(d.entries)
    for alts in d.entries.values():
        vocab.update(a for a in alts if " " not in a)
    return vocab


def normalize_for_detection(text: str) -> list[str]:
    """NFKC, drop format characters and code blocks, lower-cased word tokens.
    Character-level noise (zero-width chars, typographic variants) therefore
    cannot change the scored token sequence - by design, like a real
    token-level detector."""
    parts, pos = [], 0
    for s, e, _ in code_blocks(text):
        parts.append(text[pos:s])
        pos = e
    parts.append(text[pos:])
    clean = strip_format_chars(unicodedata.normalize("NFKC", "".join(parts)))
    return [w.lower().replace("’", "'") for w in words(clean)]


class LocalKeyedDetector(WatermarkDetector):
    name = "local-keyed-testbed"

    def __init__(self, key: bytes, gamma: float = 0.5, scope: str = "lexical_slots",
                 z_threshold: float = 4.0, min_scored: int = 16) -> None:
        if scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}")
        if not 0 < gamma < 1:
            raise ValueError("gamma must be in (0, 1)")
        self.key, self.gamma, self.scope = key, gamma, scope
        self.z_threshold, self.min_scored = z_threshold, min_scored
        self._vocab = slot_vocabulary() if scope == "lexical_slots" else None

    def score_tokens(self, toks: list[str]) -> tuple[int, int]:
        seen: set[tuple[str, str]] = set()
        green = total = 0
        for i in range(1, len(toks)):
            ctx, tok = toks[i - 1], toks[i]
            if self._vocab is not None and tok not in self._vocab:
                continue
            if (ctx, tok) in seen:
                continue
            seen.add((ctx, tok))
            total += 1
            green += green_value(self.key, ctx, tok) < self.gamma
        return green, total

    def detect(self, text: str) -> DetectionResult:
        green, total = self.score_tokens(normalize_for_detection(text))
        meta = {"green": green, "scored": total, "gamma": self.gamma, "scope": self.scope,
                "z_threshold": self.z_threshold,
                "note": "Synthetic testbed detector with a user-chosen key. NOT Claude's detector."}
        if total < self.min_scored:
            meta["reason"] = f"too few scored tokens ({total} < {self.min_scored})"
            return DetectionResult(None, None, None, None, self.name, meta)
        z = (green - self.gamma * total) / math.sqrt(total * self.gamma * (1 - self.gamma))
        p = 0.5 * math.erfc(z / math.sqrt(2))
        return DetectionResult(z >= self.z_threshold, round(z, 4), p, round(1 - p, 6), self.name, meta)

    def describe(self):
        return {**super().describe(), "scope": self.scope, "gamma": self.gamma,
                "z_threshold": self.z_threshold,
                "key_fingerprint": hashlib.sha256(self.key).hexdigest()[:12],
                "note": "Synthetic testbed detector. Cannot detect Claude's watermark."}
