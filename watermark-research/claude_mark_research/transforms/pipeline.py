"""Deterministic transformation pipelines.

A pipeline is an ordered list of stages. Each stage sees the previous stage's
output. The same input + configuration always yields the same output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..protect import ProtectionConfig
from ..textutil import anchored_edit_distance, changed_sentence_count, changed_word_count
from .base import Edit, Transform, TransformResult
from .deterministic_rewrite import DeterministicRewrite
from .lexical_substitution import LexicalSubstitution
from .phrase_substitution import PhraseSubstitution
from .punctuation import PunctuationNormalization
from .sentence_rules import SentenceRules
from .unicode_normalization import UnicodeNormalization
from .whitespace import WhitespaceNormalization

PRESETS: dict[str, list[str]] = {
    # Phrase and sentence rules run before single-word substitution so that
    # their surface patterns ("in order to", ", because") are still intact.
    "conservative": ["unicode-nfc", "whitespace", "punctuation", "phrase", "lexical"],
    "aggressive": ["unicode-nfkc", "whitespace", "punctuation", "phrase", "sentence",
                   "lexical-strong", "rewrite"],
}

#: Stages that must never be applied silently (need --interactive or --confirm-aggressive).
AGGRESSIVE_STAGES = {"lexical-strong", "sentence", "rewrite"}


@dataclass
class PipelineConfig:
    seed: int = 0
    lexical_strategy: str = "hash"
    punctuation_mode: str = "normalized"
    unicode_form: str = "NFKC"
    strip_invisible: bool = False
    transform_code: bool = False
    protect_quotes: bool = True
    substitutions_path: str | None = None
    phrases_path: str | None = None
    light_budget: float = 0.04
    moderate_budget: float = 0.10
    rewrite_mode: str = "expand"

    def protection(self) -> ProtectionConfig:
        return ProtectionConfig.build(transform_code=self.transform_code, protect_quotes=self.protect_quotes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def expand_stage_names(spec: str | list[str]) -> list[str]:
    names = spec.split(",") if isinstance(spec, str) else list(spec)
    out: list[str] = []
    for n in (x.strip().lower() for x in names):
        if not n:
            continue
        out.extend(PRESETS.get(n, [n]))
    return out


def make_stage(name: str, cfg: PipelineConfig) -> Transform:
    prot = cfg.protection()
    lex = dict(strategy=cfg.lexical_strategy, seed=cfg.seed, dictionary_path=cfg.substitutions_path,
               protection=prot)
    if name == "unicode":
        return UnicodeNormalization(cfg.unicode_form, cfg.strip_invisible, protection=prot)
    if name.startswith("unicode-"):
        return UnicodeNormalization(name.split("-", 1)[1], cfg.strip_invisible, protection=prot)
    if name == "strip-invisible":
        return UnicodeNormalization("NONE", True, protection=prot)
    if name == "whitespace":
        return WhitespaceNormalization(protection=prot)
    if name == "punctuation":
        return PunctuationNormalization(cfg.punctuation_mode, protection=prot)
    if name == "lexical":
        return LexicalSubstitution(tiers=["conservative"], **lex)
    if name == "lexical-light":
        return LexicalSubstitution(tiers=["conservative"], max_word_ratio=cfg.light_budget, **lex)
    if name == "lexical-moderate":
        return LexicalSubstitution(tiers=["conservative", "extended"], max_word_ratio=cfg.moderate_budget, **lex)
    if name == "lexical-strong":
        return LexicalSubstitution(tiers=["conservative", "extended"], **lex)
    if name == "phrase":
        return PhraseSubstitution(seed=cfg.seed, phrases_path=cfg.phrases_path, protection=prot)
    if name == "sentence":
        return SentenceRules(protection=prot)
    if name == "rewrite":
        return DeterministicRewrite(cfg.rewrite_mode, protection=prot)
    raise ValueError(f"unknown pipeline stage {name!r}")


STAGE_NAMES = ["unicode", "unicode-nfc", "unicode-nfkc", "unicode-nfd", "unicode-nfkd", "strip-invisible",
               "whitespace", "punctuation", "lexical", "lexical-light", "lexical-moderate", "lexical-strong",
               "phrase", "sentence", "rewrite"]


@dataclass
class PipelineResult:
    input_text: str
    output_text: str
    stage_names: list[str]
    stages: list[TransformResult] = field(default_factory=list)

    @property
    def edits(self) -> list[tuple[int, Edit]]:
        return [(i, e) for i, st in enumerate(self.stages) for e in st.edits]

    def audit_log(self) -> list[dict[str, Any]]:
        log = []
        for i, st in enumerate(self.stages):
            for entry in st.audit_log(stage=i):
                entry["stage_name"] = self.stage_names[i]
                log.append(entry)
        return log

    def summary(self) -> dict[str, Any]:
        a, b = self.input_text, self.output_text
        return {
            "stages": self.stage_names,
            "changed_characters": sum(s.changed_characters for s in self.stages),
            "changed_words": changed_word_count(a, b),
            "changed_sentences": changed_sentence_count(a, b),
            "transformed_sentences": sum(1 for _, e in self.edits if e.operation == "sentence_transformation"),
            "edit_distance": anchored_edit_distance(a, b),
            "edit_count": sum(len(s.edits) for s in self.stages),
            "per_stage": [s.to_dict() for s in self.stages],
        }


class Pipeline:
    def __init__(self, spec: str | list[str], config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self.stage_names = expand_stage_names(spec)
        self.stages = [make_stage(n, self.config) for n in self.stage_names]

    @property
    def is_aggressive(self) -> bool:
        return any(n in AGGRESSIVE_STAGES for n in self.stage_names)

    def describe(self) -> list[dict[str, Any]]:
        return [{"stage": n, "transformation": s.name, "parameters": s.parameters()}
                for n, s in zip(self.stage_names, self.stages)]

    def run(self, text: str, approve: Callable[[int, str, Edit], bool] | None = None) -> PipelineResult:
        result = PipelineResult(text, text, self.stage_names)
        cur = text
        for i, (name, stage) in enumerate(zip(self.stage_names, self.stages)):
            cb = (lambda e, i=i, name=name: approve(i, name, e)) if approve else None
            res = stage.transform(cur, approve=cb)
            result.stages.append(res)
            cur = res.output_text
        result.output_text = cur
        return result
