"""Transformation strength defined by measured edits (not by intent).

A transformation's strength is the highest level reached by any of three
measured ratios: word replacement ratio, character edit ratio and sentence
transformation ratio (sentences restructured by rule-based sentence
transformations; ``None`` when unknown, e.g. comparing two arbitrary files).
Thresholds are configurable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

LEVELS = ("NONE", "LIGHT", "MODERATE", "STRONG")


@dataclass
class StrengthThresholds:
    # A ratio <= light is LIGHT, <= moderate is MODERATE, above is STRONG.
    word_light: float = 0.05
    word_moderate: float = 0.20
    char_light: float = 0.05
    char_moderate: float = 0.20
    sentence_light: float = 0.10
    sentence_moderate: float = 0.40

    @classmethod
    def parse(cls, spec: str | None) -> "StrengthThresholds":
        """Parse "word_light=0.05,word_moderate=0.2,..." overrides."""
        t = cls()
        if not spec:
            return t
        for part in spec.split(","):
            if not part.strip():
                continue
            k, _, v = part.partition("=")
            k = k.strip()
            if not hasattr(t, k):
                raise ValueError(f"unknown threshold {k!r}; valid: {list(asdict(t))}")
            setattr(t, k, float(v))
        return t

    def to_dict(self) -> dict:
        return asdict(self)


def _level(ratio: float, light: float, moderate: float) -> int:
    if ratio <= 0:
        return 0
    if ratio <= light:
        return 1
    if ratio <= moderate:
        return 2
    return 3


def classify(changed_words: int, total_words: int, edit_distance: int, total_chars: int,
             transformed_sentences: int | None, total_sentences: int,
             thresholds: StrengthThresholds | None = None) -> dict:
    t = thresholds or StrengthThresholds()
    wr = changed_words / max(1, total_words)
    cr = edit_distance / max(1, total_chars)
    sr = None if transformed_sentences is None else transformed_sentences / max(1, total_sentences)
    levels = {
        "word_replacement_ratio": _level(wr, t.word_light, t.word_moderate),
        "char_edit_ratio": _level(cr, t.char_light, t.char_moderate),
    }
    if sr is not None:
        levels["sentence_transformation_ratio"] = _level(sr, t.sentence_light, t.sentence_moderate)
    top = max(levels.values())
    return {
        "strength": LEVELS[top],
        "ratios": {"word_replacement_ratio": round(wr, 4), "char_edit_ratio": round(cr, 4),
                   "sentence_transformation_ratio": None if sr is None else round(sr, 4)},
        "per_metric_level": {k: LEVELS[v] for k, v in levels.items()},
        "thresholds": t.to_dict(),
    }
