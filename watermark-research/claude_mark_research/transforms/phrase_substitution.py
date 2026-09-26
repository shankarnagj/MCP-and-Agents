"""Static multi-word phrase substitution ("in order to" -> "to", ...).

Phrases are matched case-insensitively on word boundaries, longest first,
with any run of spaces/tabs between words. Only unprotected prose is edited.
"""

from __future__ import annotations

import re

from ..resources import Dictionary, load_phrases, stable_hash
from ..textutil import match_case
from .base import Edit, Transform


class PhraseSubstitution(Transform):
    name = "phrase_substitution"

    def __init__(self, seed: int = 0, phrases_path: str | None = None,
                 phrases: Dictionary | None = None, **kw) -> None:
        self.dictionary = phrases or load_phrases(phrases_path)
        super().__init__(seed=seed, dictionary=self.dictionary.info(), **kw)
        keys = sorted(self.dictionary.entries, key=lambda k: (-len(k), k))
        self._patterns = [
            (k, re.compile(r"(?<![\w'’-])" + r"[ \t]+".join(re.escape(w) for w in k.split()) + r"(?![\w'-])",
                           re.IGNORECASE))
            for k in keys
        ]

    def propose(self, text, spans, free):
        edits: list[Edit] = []
        for fs, fe in free:
            taken: list[tuple[int, int]] = []
            for key, pat in self._patterns:
                for m in pat.finditer(text, fs, fe):
                    s, e = m.start(), m.end()
                    if any(a < e and s < b for a, b in taken):
                        continue
                    alts = self.dictionary.entries[key]
                    alt = alts[stable_hash(self.params["seed"], key, s) % len(alts)]
                    src = m.group()
                    repl = match_case(src.split()[0], alt) if not src.isupper() else alt.upper()
                    if src[:1].islower():
                        repl = alt
                    taken.append((s, e))
                    edits.append(Edit(s, e, src, repl, "phrase_substitution", "static_phrase_table",
                                      {"phrase": key}))
        return edits
