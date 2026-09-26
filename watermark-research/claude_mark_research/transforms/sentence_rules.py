"""Conservative, pattern-restricted sentence transformations.

Only sentences that match a tightly specified surface pattern are rewritten;
anything else is left unchanged. The rules deliberately under-apply: a missed
opportunity costs nothing, an ungrammatical rewrite corrupts the text.

Rule A (``because_fronting``)
    "X, because Y."  ->  "Because Y, x."
    X and Y must be comma-free clauses; X must start with a closed-class word
    (pronoun/determiner) so that lower-casing it is safe.

Rule B (``active_to_passive``)
    "<Det> <noun> <verb-ed> <det> <noun phrase>."  ->
    "<Det> <noun phrase> was/were <verb-ed> by <det> <noun>."
    Verb must be in a whitelist of regular transitive verbs whose simple past
    equals the past participle; noun phrases are 1-3 lowercase words. Number
    agreement uses the object determiner, or is skipped when ambiguous.
"""

from __future__ import annotations

import re

from ..textutil import sentence_spans
from .base import Edit, Transform

RULES = ("because_fronting", "active_to_passive")

# Words that may begin X in rule A and are safe to lower-case.
_SAFE_STARTERS = {
    "the", "this", "that", "these", "those", "it", "we", "they", "he", "she", "you",
    "a", "an", "our", "their", "its", "his", "her", "my", "your", "some", "many",
    "most", "each", "every", "all", "there", "such", "one", "no",
}

_PASSIVE_VERBS = {
    "analyzed", "analysed", "reviewed", "updated", "measured", "validated", "recorded",
    "collected", "published", "approved", "processed", "tested", "evaluated", "examined",
    "deployed", "installed", "replaced", "removed", "created", "designed", "developed",
    "prepared", "presented", "rejected", "accepted", "submitted", "signed", "completed",
    "printed", "cleaned", "checked", "configured", "compiled", "documented", "released",
    "rewrote", "verified", "inspected", "repaired", "painted", "delivered", "requested",
}
_PASSIVE_VERBS.discard("rewrote")  # irregular; participle differs

_SUBJ_DETS = {"the", "this", "that", "our", "their", "each", "every", "a", "an", "its", "my", "your", "his", "her"}
_OBJ_DETS_SING = {"a", "an", "this", "that", "each", "every"}
_OBJ_DETS_PLUR = {"these", "those", "several", "many", "both", "all"}
_OBJ_DETS_AMBIG = {"the", "our", "their", "its", "my", "your", "his", "her"}
_PRONOUN_OBJECT = {"we": "us", "they": "them", "he": "him", "she": "her", "i": "me"}
_INVARIANT_PLURALS = {"data", "people", "criteria", "media", "series", "species", "news", "staff", "police"}
_SINGULAR_S = ("ss", "us", "is", "ics", "sis")

_A_PATTERN = re.compile(r"^(?P<x>[A-Z][^,;:()\"“”]*?[a-z0-9]), because (?P<y>[a-z][^,;:()\"“”]*?)(?P<end>[.!])$")
_B_PATTERN = re.compile(
    r"^(?P<sdet>[A-Z][a-z]*) (?:(?P<snoun>[a-z]+(?: [a-z]+)?) )?(?P<verb>[a-z]+ed) "
    r"(?P<odet>[a-z]+) (?P<onp>[a-z]+(?: [a-z]+){0,2})(?P<end>\.)$"
)


def _is_plural(det: str, head: str) -> bool | None:
    if det in _OBJ_DETS_SING:
        return False
    if det in _OBJ_DETS_PLUR:
        return True
    if head in _INVARIANT_PLURALS:
        return None
    if head.endswith("s") and not head.endswith(_SINGULAR_S):
        return True
    if head.endswith(_SINGULAR_S):
        return None
    return False


def because_fronting(sentence: str) -> str | None:
    m = _A_PATTERN.match(sentence)
    if not m:
        return None
    x, y = m.group("x"), m.group("y")
    first = x.split()[0]
    if first.lower() not in _SAFE_STARTERS or first == "I":
        return None
    if " because " in y or " because " in x.lower() or len(x.split()) < 2 or len(y.split()) < 2:
        return None
    return f"Because {y}, {first.lower()}{x[len(first):]}{m.group('end')}"


def active_to_passive(sentence: str) -> str | None:
    m = _B_PATTERN.match(sentence)
    if not m:
        return None
    sdet, snoun, verb = m.group("sdet"), m.group("snoun"), m.group("verb")
    odet, onp = m.group("odet"), m.group("onp")
    if verb not in _PASSIVE_VERBS:
        return None
    if snoun is None:
        agent = _PRONOUN_OBJECT.get(sdet.lower())
        if agent is None:
            return None
    else:
        if sdet.lower() not in _SUBJ_DETS:
            return None
        agent = f"{sdet.lower()} {snoun}"
        if any(w.endswith(("ed", "ly")) or w in {"is", "was", "has", "not", "also", "then", "just", "never",
                                                  "always", "often", "still", "already", "soon"}
               for w in snoun.split()):
            return None
    if odet not in _OBJ_DETS_SING | _OBJ_DETS_PLUR | _OBJ_DETS_AMBIG:
        return None
    if any(w.endswith(("ed", "ly")) or w in {"to", "and", "or", "of", "for", "with", "by", "in", "on"} for w in onp.split()):
        return None
    plural = _is_plural(odet, onp.split()[-1])
    if plural is None:
        return None
    aux = "were" if plural else "was"
    return f"{odet[0].upper()}{odet[1:]} {onp} {aux} {verb} by {agent}."


_RULE_FUNCS = {"because_fronting": because_fronting, "active_to_passive": active_to_passive}


class SentenceRules(Transform):
    name = "sentence_rules"

    def __init__(self, rules: list[str] | None = None, **kw) -> None:
        rules = list(rules or RULES)
        for r in rules:
            if r not in RULES:
                raise ValueError(f"unknown sentence rule {r!r}; choose from {RULES}")
        super().__init__(rules=rules, **kw)

    def propose(self, text, spans, free):
        edits: list[Edit] = []
        for s, e in sentence_spans(text):
            # Rewriting moves text around; only rewrite sentences that are
            # entirely free prose on a single line.
            if any(sp.overlaps(s, e) for sp in spans) or "\n" in text[s:e]:
                continue
            line_start = text.rfind("\n", 0, s) + 1
            prefix = text[line_start:s]
            # Skip list items / headings; allow a previous sentence on the line.
            if prefix.strip() and not re.search(r"[.!?][\"')\]\u201d\u2019]*\s+$", prefix):
                continue
            sentence = text[s:e]
            for rule in self.params["rules"]:
                out = _RULE_FUNCS[rule](sentence)
                if out and out != sentence:
                    edits.append(Edit(s, e, sentence, out, "sentence_transformation", rule))
                    break
        return edits
