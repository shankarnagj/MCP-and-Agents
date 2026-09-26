"""Interactive review: approve or reject every proposed edit, stage by stage."""

from __future__ import annotations

from typing import Callable, TextIO

from .transforms.base import Edit
from .transforms.pipeline import Pipeline, PipelineResult

_HELP = "[y] apply  [n] reject  [a] apply rest of stage  [r] reject rest of stage  [q] reject all remaining"


def _context(text_len_hint: str, e: Edit, width: int = 40) -> tuple[str, str]:
    left = text_len_hint[max(0, e.start - width):e.start].replace("\n", " ")
    right = text_len_hint[e.end:e.end + width].replace("\n", " ")
    return f"...{left}[{e.original}]{right}...", f"...{left}[{e.replacement}]{right}..."


def run_interactive(pipeline: Pipeline, text: str, input_fn: Callable[[str], str] = input,
                    out: TextIO | None = None) -> PipelineResult:
    import sys
    out = out or sys.stdout
    state = {"stage": -1, "mode": None, "quit": False, "text": text}
    stage_inputs: dict[int, str] = {}

    def approve(i: int, name: str, e: Edit) -> bool:
        if state["stage"] != i:
            state["stage"], state["mode"] = i, None
            print(f"\n=== Stage {i + 1}/{len(pipeline.stage_names)}: {name} ===", file=out)
            if name in {"lexical-strong", "sentence", "rewrite"}:
                print("    (aggressive stage - every edit needs explicit approval)", file=out)
            print(_HELP, file=out)
        if state["quit"]:
            return False
        if state["mode"] is not None:
            return state["mode"]
        src = stage_inputs.get(i, "")
        orig, new = _context(src, e)
        print(f"\nORIGINAL:    {orig}\nTRANSFORMED: {new}\nRULE: {e.operation}/{e.rule} @ {e.start}", file=out)
        while True:
            ans = input_fn("apply? ").strip().lower()[:1]
            if ans in ("y", "n"):
                return ans == "y"
            if ans == "a":
                state["mode"] = True
                return True
            if ans == "r":
                state["mode"] = False
                return False
            if ans == "q":
                state["quit"] = True
                return False
            print(_HELP, file=out)

    # Pipeline.run calls stages sequentially; record each stage input for context.
    result = PipelineResult(text, text, pipeline.stage_names)
    cur = text
    for i, (name, stage) in enumerate(zip(pipeline.stage_names, pipeline.stages)):
        stage_inputs[i] = cur
        res = stage.transform(cur, approve=lambda e, i=i, name=name: approve(i, name, e))
        result.stages.append(res)
        cur = res.output_text
    result.output_text = cur

    summ = result.summary()
    print("\n=== CHANGES ===", file=out)
    for entry in result.audit_log():
        print(f"  [{entry['stage_name']}] {entry['source']!r} -> {entry['replacement']!r} ({entry['rule']})", file=out)
    print("\n=== STATISTICS ===", file=out)
    for k in ("edit_count", "changed_words", "changed_characters", "changed_sentences", "edit_distance"):
        print(f"  {k}: {summ[k]}", file=out)
    return result
