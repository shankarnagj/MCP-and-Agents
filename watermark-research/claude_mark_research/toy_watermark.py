"""Synthetic lexical watermark embedder (testbed only, no model involved).

Purpose: give the local keyed detector something real to measure, so that the
effect of each transformation on a *token-choice* signal can be studied end
to end. It rewrites existing human-authored/synthetic text by choosing, at
each dictionary slot, the variant that is "green" under a user-chosen key and
the previous output word. Choices are deterministic (dictionary + HMAC).

This is a toy analogue of a token-selection watermark. It is NOT Claude's
watermark, and results on it do not transfer quantitatively to Claude.
"""

from __future__ import annotations

import re

from .detector.local_detector import green_value
from .protect import ProtectionConfig, code_blocks, find_protected, free_segments
from .resources import load_substitutions
from .textutil import WORD_RE, match_case
from .transforms.lexical_substitution import _article_for


def embed(text: str, key: bytes, gamma: float = 0.5) -> tuple[str, list[dict]]:
    entries = load_substitutions(tiers=["conservative", "extended"]).entries
    spans = find_protected(text, ProtectionConfig())
    free = free_segments(text, spans)
    code = [(s, e) for s, e, _ in code_blocks(text)]
    out: list[str] = []
    log: list[dict] = []
    pos = 0
    prev_word = ""
    # Walk every word the detector would see (code blocks excluded), so the
    # context word matches the detector's; only free prose words may change.
    for m in WORD_RE.finditer(text):
        if any(s <= m.start() < e for s, e in code):
            continue
        is_free = any(fs <= m.start() and m.end() <= fe for fs, fe in free)
        w = m.group()
        lw = w.lower()
        choice = w
        if is_free and lw in entries and w.isalpha() and prev_word:
            cands = [lw] + [a for a in entries[lw] if " " not in a]
            art = re.search(r"\b(a|an)\s+$", text[max(0, m.start() - 6):m.start()], re.I)
            if art:
                cands = [c for c in cands if _article_for(c) == _article_for(lw)]
            greens = [c for c in cands if green_value(key, prev_word, c) < gamma]
            if greens and lw not in greens:
                choice = match_case(w, greens[0])
                log.append({"operation": "toy_watermark_embed", "source": w, "replacement": choice,
                            "position": m.start(), "rule": "keyed_green_choice", "deterministic": True})
        out.append(text[pos:m.start()])
        out.append(choice)
        pos = m.end()
        prev_word = choice.lower().replace("\u2019", "'")
    out.append(text[pos:])
    return "".join(out), log
