"""Deterministic contraction rewriting.

``expand``   - "don't" -> "do not" (only unambiguous contractions)
``contract`` - "do not" -> "don't"

Ambiguous forms ("it's" = it is / it has, "he'd" = he had / he would,
"'s" possessive vs. "is") are never touched.
"""

from __future__ import annotations

import re

from ..textutil import match_case
from .base import Edit, Transform

MODES = ("expand", "contract")

_UNAMBIGUOUS = {
    "don't": "do not", "doesn't": "does not", "didn't": "did not",
    "can't": "cannot", "couldn't": "could not", "shouldn't": "should not",
    "wouldn't": "would not", "won't": "will not", "isn't": "is not",
    "aren't": "are not", "wasn't": "was not", "weren't": "were not",
    "haven't": "have not", "hasn't": "has not", "hadn't": "had not",
    "mustn't": "must not", "needn't": "need not",
    "i'm": "I am", "you're": "you are", "we're": "we are", "they're": "they are",
    "i've": "I have", "you've": "you have", "we've": "we have", "they've": "they have",
    "i'll": "I will", "you'll": "you will", "we'll": "we will", "they'll": "they will",
    "let's": "let us",
}
_CONTRACT = {v.lower(): k for k, v in _UNAMBIGUOUS.items() if k != "let's"}


class DeterministicRewrite(Transform):
    name = "deterministic_rewrite"

    def __init__(self, mode: str = "expand", **kw) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown rewrite mode {mode!r}; choose from {MODES}")
        super().__init__(mode=mode, **kw)
        if mode == "expand":
            keys = sorted(_UNAMBIGUOUS, key=len, reverse=True)
            self._pat = re.compile(r"(?<![\w'])(" + "|".join(re.escape(k).replace("'", "['’]") for k in keys) + r")(?![\w'])",
                                   re.IGNORECASE)
        else:
            keys = sorted(_CONTRACT, key=len, reverse=True)
            self._pat = re.compile(r"(?<![\w'])(" + "|".join(r"[ \t]+".join(re.escape(w) for w in k.split()) for k in keys) + r")(?![\w'])",
                                   re.IGNORECASE)

    def propose(self, text, spans, free):
        edits: list[Edit] = []
        for fs, fe in free:
            for m in self._pat.finditer(text, fs, fe):
                src = m.group()
                if self.params["mode"] == "expand":
                    key = src.lower().replace("’", "'")
                    repl = _UNAMBIGUOUS[key]
                    if not repl.startswith("I "):
                        repl = match_case(src, repl) if not src.isupper() else repl.upper()
                    rule = "expand_contraction"
                else:
                    key = " ".join(src.lower().split())
                    repl = _CONTRACT[key]
                    if repl.startswith("i'"):
                        repl = "I" + repl[1:]
                    else:
                        repl = match_case(src, repl) if not src.isupper() else repl.upper()
                    rule = "contract"
                if repl != src:
                    edits.append(Edit(m.start(), m.end(), src, repl, "deterministic_rewrite", rule))
        return edits
