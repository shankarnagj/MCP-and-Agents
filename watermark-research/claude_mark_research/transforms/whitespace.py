"""Deterministic whitespace normalisation.

* runs of spaces/tabs inside a line collapse to a single space
* trailing whitespace on a line is removed
* exotic spaces (NBSP, en/em spaces, ...) become ASCII space (optional)
* three or more consecutive line breaks collapse to one blank line
* leading indentation is preserved (Markdown nesting depends on it)
"""

from __future__ import annotations

import re

from .base import Edit, Transform

_UNUSUAL_SPACES = "               　"


class WhitespaceNormalization(Transform):
    name = "whitespace_normalization"

    def __init__(self, unusual_spaces: bool = True, collapse_blank_lines: bool = True,
                 strip_trailing: bool = True, **kw) -> None:
        super().__init__(unusual_spaces=unusual_spaces, collapse_blank_lines=collapse_blank_lines,
                         strip_trailing=strip_trailing, **kw)

    def propose(self, text, spans, free):
        p = self.params
        edits: list[Edit] = []
        unusual = _UNUSUAL_SPACES if p["unusual_spaces"] else ""
        sp_class = "[ \\t" + unusual + "]"
        rules = []
        if p["collapse_blank_lines"]:
            rules.append(("blank_lines", re.compile(r"(?:[ \t]*\r?\n){3,}")))
        if p["strip_trailing"]:
            rules.append(("trailing", re.compile(sp_class + r"+(?=\r?\n|$)")))
        # Inner runs only: never at the start of a line (indentation is kept).
        rules.append(("inner_run", re.compile(r"(?<=\S)" + sp_class + r"{2,}|(?<=\S)[\t" + unusual + "]")))
        for fs, fe in free:
            taken: list[tuple[int, int]] = []
            for rule, pat in rules:
                for m in pat.finditer(text, fs, fe):
                    s, e = m.start(), m.end()
                    if any(a < e and s < b for a, b in taken):
                        continue
                    repl = {"blank_lines": "\n\n", "trailing": ""}.get(rule, " ")
                    if rule == "trailing" and e < len(text) and e == fe:
                        # Whitespace before a protected span is not "trailing".
                        continue
                    if repl != m.group():
                        taken.append((s, e))
                        edits.append(Edit(s, e, m.group(), repl, "whitespace_normalization", rule))
        return edits
