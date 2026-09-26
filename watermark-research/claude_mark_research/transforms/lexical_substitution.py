"""Static, context-safe lexical substitution from a local dictionary.

No model selects substitutions. For a word with several dictionary
alternatives the choice is made by one of three deterministic strategies:

* ``first``        - always the first alternative
* ``hash``         - sha256(seed, headword, position) mod n
* ``round_robin``  - cycles through alternatives per headword, in text order

The amount of change is controlled by ``rate`` (fraction of eligible
occurrences, chosen by a seeded hash rank) and ``max_word_ratio`` (a hard cap
on substitutions relative to the number of words in the text).
"""

from __future__ import annotations

import re

from ..resources import Dictionary, load_substitutions, stable_hash
from ..textutil import WORD_RE, match_case, words
from .base import Edit, Transform

STRATEGIES = ("first", "hash", "round_robin")

_AUXILIARIES = {"has", "have", "had", "having", "been", "be", "being", "is", "are", "was", "were"}
_IRREGULAR_PRETERITES = {"showed", "began"}
_AN_EXCEPTIONS_A = ("use", "usu", "uni", "eu", "one", "once", "ubi")
_AN_EXCEPTIONS_AN = ("hour", "honest", "honor", "honour", "heir")


def _article_for(word: str) -> str:
    w = word.lower()
    if w.startswith(_AN_EXCEPTIONS_AN):
        return "an"
    if w.startswith(_AN_EXCEPTIONS_A):
        return "a"
    return "an" if w[:1] in "aeiou" else "a"


class LexicalSubstitution(Transform):
    name = "lexical_substitution"

    def __init__(self, strategy: str = "hash", seed: int = 0, rate: float = 1.0,
                 max_word_ratio: float | None = None, tiers: list[str] | None = None,
                 dictionary_path: str | None = None, dictionary: Dictionary | None = None, **kw) -> None:
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown lexical strategy {strategy!r}; choose from {STRATEGIES}")
        if not 0.0 <= rate <= 1.0:
            raise ValueError("rate must be within [0, 1]")
        self.dictionary = dictionary or load_substitutions(dictionary_path, tiers)
        super().__init__(strategy=strategy, seed=seed, rate=rate, max_word_ratio=max_word_ratio,
                         tiers=self.dictionary.tiers, dictionary=self.dictionary.info(), **kw)

    def _choose(self, head: str, alts: list[str], pos: int, counters: dict[str, int]) -> str:
        strategy = self.params["strategy"]
        if strategy == "first" or len(alts) == 1:
            return alts[0]
        if strategy == "hash":
            return alts[stable_hash(self.params["seed"], head, pos) % len(alts)]
        i = counters.get(head, 0)
        counters[head] = i + 1
        return alts[(i + self.params["seed"]) % len(alts)]

    def propose(self, text, spans, free):
        entries = self.dictionary.entries
        candidates: list[tuple[int, int, str]] = []
        for fs, fe in free:
            for m in WORD_RE.finditer(text, fs, fe):
                w = m.group()
                if w.lower() not in entries or not entries[w.lower()]:
                    continue
                s, e = m.start(), m.end()
                before = text[s - 1] if s > 0 else " "
                after = text[e] if e < len(text) else " "
                # Parts of compounds, identifiers, hashtags, mentions: skip.
                if before in "-_/@#.\\'’" or after in "-_/\\@'’" or (after == "." and e + 1 < len(text) and text[e + 1].isalnum()):
                    continue
                if not w.isalpha():
                    continue
                # Mixed-case words (e.g. "iPhone") are proper nouns / brands.
                if not (w.islower() or w.isupper() or (w[0].isupper() and w[1:].islower())):
                    continue
                candidates.append((s, e, w))

        selected = candidates
        n_words = max(1, len(words(text)))
        rate = self.params["rate"]
        cap = self.params["max_word_ratio"]
        limit = len(candidates)
        if rate < 1.0:
            limit = min(limit, int(round(rate * len(candidates))))
        if cap is not None:
            limit = min(limit, int(cap * n_words))
        if limit < len(candidates):
            ranked = sorted(candidates, key=lambda c: stable_hash(self.params["seed"], "select", c[0], c[2].lower()))
            keep = {c[0] for c in ranked[:limit]}
            selected = [c for c in candidates if c[0] in keep]

        counters: dict[str, int] = {}
        edits: list[Edit] = []
        for s, e, w in selected:
            head = w.lower()
            alt = self._choose(head, entries[head], s, counters)
            prev = re.search(r"(\w+)\s+$", text[max(0, s - 40):s])
            prev_word = prev.group(1) if prev else ""
            if alt in _IRREGULAR_PRETERITES and prev_word.lower() in _AUXILIARIES:
                continue
            repl = match_case(w, alt)
            meta = {"strategy": self.params["strategy"], "alternatives": entries[head]}
            # Keep a/an agreement when the preceding word is an article.
            art = re.search(r"\b(a|an|A|An|AN)(\s+)$", text[max(0, s - 10):s])
            if art:
                want = _article_for(alt)
                if want != art.group(1).lower():
                    a_start = s - len(art.group(1)) - len(art.group(2))
                    if not any(sp.overlaps(a_start, s) for sp in spans):
                        new_art = match_case(art.group(1), want)
                        edits.append(Edit(a_start, e, text[a_start:e], new_art + art.group(2) + repl,
                                          "lexical_substitution", "static_dictionary+article_agreement",
                                          {**meta, "headword": head}))
                        continue
            edits.append(Edit(s, e, w, repl, "lexical_substitution", "static_dictionary", meta))
        return edits
