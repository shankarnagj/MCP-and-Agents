"""Deterministic punctuation normalisation.

Modes (``--punctuation``):

* ``normalized``  - typographic quotes/apostrophes -> ASCII, dash variants ->
  ASCII, ellipsis character -> "...", repeated punctuation collapsed, spaces
  before closing punctuation removed.
* ``typographic`` - ASCII quotes/apostrophes -> typographic, " -- " -> em dash.
* ``keep``        - no quote/dash changes; only spacing + repeated punctuation.
"""

from __future__ import annotations

import re

from .base import Edit, Transform

MODES = ("normalized", "typographic", "keep")

_TO_ASCII = {
    "“": '"', "”": '"', "„": '"', "‟": '"', "«": '"', "»": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "--", "―": "--",
    "…": "...",
}


class PunctuationNormalization(Transform):
    name = "punctuation_normalization"

    def __init__(self, mode: str = "normalized", quotes: bool = True, dashes: bool = True,
                 repeated: bool = True, spacing: bool = True, **kw) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown punctuation mode {mode!r}; choose from {MODES}")
        super().__init__(mode=mode, quotes=quotes, dashes=dashes, repeated=repeated,
                         spacing=spacing, **kw)

    def _char_edits(self, text: str, fs: int, fe: int) -> list[Edit]:
        p = self.params
        edits: list[Edit] = []
        if p["mode"] == "normalized":
            for i in range(fs, fe):
                ch = text[i]
                repl = _TO_ASCII.get(ch)
                if repl is None:
                    continue
                is_quote = ch in "“”„‟«»‘’‚‛′"
                if is_quote and not p["quotes"]:
                    continue
                if not is_quote and ch != "…" and not p["dashes"]:
                    continue
                if ch == "…" and not p["repeated"]:
                    continue
                rule = "apostrophe" if ch == "’" and 0 < i < len(text) - 1 and text[i - 1].isalpha() and text[i + 1].isalpha() \
                    else ("quote" if is_quote else ("ellipsis" if ch == "…" else "dash"))
                edits.append(Edit(i, i + 1, ch, repl, "punctuation_normalization", f"to_ascii_{rule}"))
        elif p["mode"] == "typographic":
            if p["quotes"]:
                for i in range(fs, fe):
                    ch = text[i]
                    if ch not in "\"'":
                        continue
                    prev = text[i - 1] if i > 0 else " "
                    nxt = text[i + 1] if i + 1 < len(text) else " "
                    if ch == "'" and prev.isalnum() and nxt.isalpha():
                        repl, rule = "’", "apostrophe"
                    elif prev.isspace() or prev in "([{—-" or i == 0:
                        repl, rule = ("“" if ch == '"' else "‘"), "open_quote"
                    else:
                        repl, rule = ("”" if ch == '"' else "’"), "close_quote"
                    edits.append(Edit(i, i + 1, ch, repl, "punctuation_normalization", f"to_typographic_{rule}"))
            if p["dashes"]:
                for m in re.finditer(r"(?<=\w) -- (?=\w)", text[fs:fe]):
                    edits.append(Edit(fs + m.start(), fs + m.end(), m.group(), "—",
                                      "punctuation_normalization", "to_typographic_em_dash"))
        return edits

    def propose(self, text, spans, free):
        p = self.params
        edits: list[Edit] = []
        for fs, fe in free:
            taken: list[tuple[int, int]] = []
            if p["repeated"]:
                for m in re.finditer(r"([!?,;:])\1+|\.{4,}", text[fs:fe]):
                    s, e = fs + m.start(), fs + m.end()
                    repl = "..." if m.group().startswith(".") else m.group(1)
                    taken.append((s, e))
                    edits.append(Edit(s, e, m.group(), repl, "punctuation_normalization", "repeated_punctuation"))
            if p["spacing"]:
                for m in re.finditer(r"(?<=\w)[ \t]+(?=[,;:!?)\]](?:\s|$))|(?<=[(\[])[ \t]+(?=\w)", text[fs:fe]):
                    s, e = fs + m.start(), fs + m.end()
                    if any(a < e and s < b for a, b in taken):
                        continue
                    taken.append((s, e))
                    edits.append(Edit(s, e, m.group(), "", "punctuation_normalization", "space_around_punctuation"))
            for ed in self._char_edits(text, fs, fe):
                if not any(a < ed.end and ed.start < b for a, b in taken):
                    edits.append(ed)
        return edits
