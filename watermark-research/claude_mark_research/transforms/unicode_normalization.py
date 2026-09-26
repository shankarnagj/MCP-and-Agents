"""Unicode normalisation (NFC/NFKC/NFD/NFKD) and invisible-character stripping.

CONTROL EXPERIMENT. These operations change the *encoding* of text, not the
words chosen. A token-selection watermark such as SynthID-Text lives in the
choice of words, so these transformations are not expected to remove it.
They are labelled "Unicode normalization experiment", never "watermark removal".
"""

from __future__ import annotations

import re
import unicodedata

from ..unicode_diag import INVISIBLE_CATEGORIES, classify_char
from .base import Edit, Transform

FORMS = ("NFC", "NFKC", "NFD", "NFKD", "NONE")


class UnicodeNormalization(Transform):
    name = "unicode_normalization"
    label = "Unicode normalization experiment"

    def __init__(self, form: str = "NFC", strip_invisible: bool = False, **kw) -> None:
        form = form.upper()
        if form not in FORMS:
            raise ValueError(f"unknown Unicode form {form!r}; choose from {FORMS}")
        super().__init__(form=form, strip_invisible=strip_invisible, **kw)
        self.form = form
        self.strip_invisible = strip_invisible

    def parameters(self):
        p = super().parameters()
        p["label"] = self.label
        return p

    def propose(self, text, spans, free):
        edits: list[Edit] = []
        for fs, fe in free:
            for m in re.finditer(r"\S+|\s+", text[fs:fe]):
                chunk = m.group()
                start = fs + m.start()
                if self.strip_invisible:
                    # Emit one edit per invisible character.
                    pieces = []
                    offset = 0
                    for i, ch in enumerate(chunk):
                        kind = classify_char(ch)
                        if kind in INVISIBLE_CATEGORIES:
                            if i > offset:
                                pieces.append((offset, i))
                            edits.append(Edit(start + i, start + i + 1, ch, "", "strip_invisible",
                                              "unicode_invisible_removal",
                                              {"codepoint": f"U+{ord(ch):04X}", "category": kind}))
                            offset = i + 1
                    if offset < len(chunk):
                        pieces.append((offset, len(chunk)))
                else:
                    pieces = [(0, len(chunk))]
                for ps, pe in pieces:
                    sub = chunk[ps:pe]
                    norm = sub if self.form == "NONE" else unicodedata.normalize(self.form, sub)
                    if norm != sub:
                        edits.append(Edit(start + ps, start + pe, sub, norm, "unicode_normalization",
                                          f"unicode_{self.form.lower()}"))
        return edits
