"""Common transformation interface.

Every transformation first *proposes* a list of non-overlapping edits against
its input and then applies them. Keeping edits explicit gives:

* an audit log entry per edit (source, replacement, position, rule),
* exact per-edit metrics (changed characters, edit distance),
* the ability to approve/reject individual edits in interactive mode.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..protect import ProtectionConfig, Span, find_protected, free_segments
from ..textutil import changed_sentence_count, changed_word_count, levenshtein


@dataclass
class Edit:
    start: int
    end: int
    original: str
    replacement: str
    operation: str
    rule: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def audit(self, stage: int | None = None) -> dict[str, Any]:
        entry = {
            "operation": self.operation,
            "source": self.original,
            "replacement": self.replacement,
            "position": self.start,
            "end": self.end,
            "rule": self.rule,
            "deterministic": True,
        }
        if stage is not None:
            entry["stage"] = stage
        if self.metadata:
            entry["metadata"] = self.metadata
        return entry


@dataclass
class TransformResult:
    output_text: str
    changed_characters: int
    changed_words: int
    changed_sentences: int
    edit_distance: int
    transformation_name: str
    parameters: dict[str, Any]
    edits: list[Edit] = field(default_factory=list)
    input_text: str = ""

    def to_dict(self, include_text: bool = False) -> dict[str, Any]:
        d = {
            "transformation_name": self.transformation_name,
            "parameters": self.parameters,
            "changed_characters": self.changed_characters,
            "changed_words": self.changed_words,
            "changed_sentences": self.changed_sentences,
            "edit_distance": self.edit_distance,
            "edit_count": len(self.edits),
        }
        if include_text:
            d["output_text"] = self.output_text
        return d

    def audit_log(self, stage: int | None = None) -> list[dict[str, Any]]:
        return [e.audit(stage) for e in self.edits]


def apply_edits(text: str, edits: list[Edit]) -> str:
    out = []
    pos = 0
    for e in sorted(edits, key=lambda e: e.start):
        if e.start < pos:
            raise ValueError(f"overlapping edits at {e.start}")
        out.append(text[pos:e.start])
        out.append(e.replacement)
        pos = e.end
    out.append(text[pos:])
    return "".join(out)


def build_result(name: str, params: dict[str, Any], text: str, edits: list[Edit]) -> TransformResult:
    edits = sorted(edits, key=lambda e: e.start)
    output = apply_edits(text, edits)
    return TransformResult(
        output_text=output,
        changed_characters=sum(max(len(e.original), len(e.replacement)) for e in edits),
        changed_words=changed_word_count(text, output) if edits else 0,
        changed_sentences=changed_sentence_count(text, output) if edits else 0,
        edit_distance=sum(levenshtein(e.original, e.replacement) for e in edits),
        transformation_name=name,
        parameters=params,
        edits=edits,
        input_text=text,
    )


class Transform:
    """Base class. Subclasses implement `propose(text, spans, free)`."""

    name = "base"
    #: True for transformations that touch protected spans' neighbourhoods only
    aggressive = False

    def __init__(self, protection: ProtectionConfig | None = None, **params: Any) -> None:
        self.protection = protection or ProtectionConfig()
        self.params = params

    def parameters(self) -> dict[str, Any]:
        return dict(self.params)

    def propose(self, text: str, spans: list[Span], free: list[tuple[int, int]]) -> list[Edit]:
        raise NotImplementedError

    def proposals(self, text: str) -> list[Edit]:
        spans = find_protected(text, self.protection)
        edits = self.propose(text, spans, free_segments(text, spans))
        # Safety net: never emit an edit touching a protected span.
        return [e for e in edits if not any(s.overlaps(e.start, max(e.end, e.start + 1)) and
                                            not (e.start == e.end == s.start) for s in spans)]

    def transform(self, text: str, approve: Callable[[Edit], bool] | None = None) -> TransformResult:
        edits = self.proposals(text)
        if approve is not None:
            edits = [e for e in edits if approve(e)]
        return build_result(self.name, self.parameters(), text, edits)


def dataclass_dict(obj: Any) -> dict[str, Any]:
    return asdict(obj)
