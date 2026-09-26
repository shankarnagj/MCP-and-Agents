"""Experiment matrix: run every transformation, measure change, query detector.

Scientific rule enforced here: a change in text is never reported as
"watermark removed". Detector-derived fields are filled only from a
configured detector; otherwise they are null and the status is UNKNOWN.
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import COMPONENT_VERSIONS
from .baseline import analyze
from .detector import NoDetector, WatermarkDetector
from .detector.base import DetectionResult
from .resources import load_phrases, load_substitutions
from .similarity import compare
from .strength import StrengthThresholds, classify
from .textutil import sentences, words
from .transforms.pipeline import Pipeline, PipelineConfig


@dataclass
class ExperimentSpec:
    id: str
    name: str
    stages: list[str]
    config_overrides: dict[str, Any] = field(default_factory=dict)
    note: str = ""


EXPERIMENT_MATRIX = [
    ExperimentSpec("A", "original", [], note="Untransformed input (reference)."),
    ExperimentSpec("B", "unicode_normalization", ["strip-invisible", "unicode-nfkc"],
                   note="Unicode normalization experiment (control): NFKC + invisible-character stripping."),
    ExperimentSpec("C", "whitespace_normalization", ["whitespace"], note="Control."),
    ExperimentSpec("D", "punctuation_normalization", ["punctuation"], note="Control."),
    ExperimentSpec("E", "lexical_light", ["lexical-light"], note="Target: LIGHT (word budget capped)."),
    ExperimentSpec("F", "lexical_moderate", ["lexical-moderate"], note="Target: MODERATE (word budget capped, extended tier)."),
    ExperimentSpec("G", "lexical_strong", ["lexical-strong"], note="Target: STRONG (all eligible, extended tier)."),
    ExperimentSpec("H", "phrase_substitution", ["phrase"]),
    ExperimentSpec("I", "combined_conservative", ["conservative"]),
    ExperimentSpec("J", "combined_aggressive", ["aggressive"]),
]

CSV_COLUMNS = [
    "experiment_id", "transformation", "strength", "words_changed", "chars_changed", "edit_distance",
    "tfidf_similarity", "char_ngram_similarity", "preservation_score",
    "watermark_score_before", "watermark_score_after", "p_value_before", "p_value_after",
    "detected_before", "detected_after", "detection_status_before", "detection_status_after",
    "detector", "detector_is_mock",
]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _signal_change(before: DetectionResult, after: DetectionResult) -> float | None:
    if before.is_mock or after.is_mock or before.score is None or after.score is None:
        return None
    return round(after.score - before.score, 6)


def interpret(before: DetectionResult, after: DetectionResult, detector: WatermarkDetector) -> str:
    if isinstance(detector, NoDetector):
        return "DETECTION STATUS: UNKNOWN (no detector configured)."
    if before.is_mock:
        return "DETECTION STATUS: UNKNOWN (mock detector; output is synthetic and not evidence)."
    if before.status == "UNKNOWN" or after.status == "UNKNOWN":
        return "DETECTION STATUS: UNKNOWN (detector returned no decision)."
    scope = "" if detector.authoritative else " (testbed detector - says nothing about Claude's watermark)"
    if before.status == "DETECTED" and after.status == "NOT_DETECTED":
        return ("Detector no longer flags the transformed text at its threshold" + scope +
                ". This is a single measurement, not proof of removal; check effect size and repeat.")
    if before.status == "DETECTED" and after.status == "DETECTED":
        return "Signal still detected after transformation" + scope + "."
    if before.status == "NOT_DETECTED":
        return "Original was not detected, so the transformation's effect on the signal cannot be assessed" + scope + "."
    return f"before={before.status}, after={after.status}{scope}."


def run_experiments(text: str, detector: WatermarkDetector | None = None,
                    config: PipelineConfig | None = None,
                    thresholds: StrengthThresholds | None = None,
                    matrix: list[ExperimentSpec] | None = None,
                    source_name: str = "input", extra_meta: dict | None = None) -> dict[str, Any]:
    detector = detector or NoDetector()
    config = config or PipelineConfig()
    thresholds = thresholds or StrengthThresholds()
    matrix = matrix or EXPERIMENT_MATRIX
    total_words, total_chars, total_sents = len(words(text)), len(text), len(sentences(text))

    det_before = detector.detect(text)
    results = []
    for spec in matrix:
        cfg = PipelineConfig(**{**config.to_dict(), **spec.config_overrides})
        pipe = Pipeline(spec.stages, cfg)
        pres = pipe.run(text)
        summ = pres.summary()
        sim = compare(text, pres.output_text)
        strength = classify(summ["changed_words"], total_words, summ["edit_distance"], total_chars,
                            summ["transformed_sentences"], total_sents, thresholds)
        det_after = det_before if pres.output_text == text else detector.detect(pres.output_text)
        results.append({
            "id": spec.id,
            "name": spec.name,
            "note": spec.note,
            "pipeline": pipe.stage_names,
            "pipeline_detail": pipe.describe(),
            "aggressive": pipe.is_aggressive,
            "metrics": {k: v for k, v in summ.items() if k != "per_stage"},
            "per_stage": summ["per_stage"],
            "strength": strength,
            "similarity": sim,
            "detection_before": det_before.to_dict(),
            "detection_after": det_after.to_dict(),
            "signal_change": _signal_change(det_before, det_after),
            "text_change": strength["ratios"]["word_replacement_ratio"],
            "preservation_score": sim["preservation_score"],
            "interpretation": interpret(det_before, det_after, detector),
            "output_sha256": sha256(pres.output_text),
            "output_text": pres.output_text,
            "audit_log": pres.audit_log(),
        })

    subs = load_substitutions(config.substitutions_path, ["conservative", "extended"])
    phr = load_phrases(config.phrases_path)
    return {
        "tool": "claude-mark-research",
        "research_question": ("How robust is a statistical Claude-style token watermark to deterministic, "
                              "non-generative text transformations?"),
        "source": source_name,
        "input_sha256": sha256(text),
        "baseline": analyze(text),
        "detector": detector.describe(),
        "overall_detection_status": det_before.status,
        "experiments": results,
        "reproducibility": {
            "seed": config.seed,
            "configuration": config.to_dict(),
            "strength_thresholds": thresholds.to_dict(),
            "transformation_versions": COMPONENT_VERSIONS,
            "dictionary": subs.info(),
            "phrase_table": phr.info(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            **(extra_meta or {}),
        },
    }


def csv_rows(exp: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for r in exp["experiments"]:
        b, a = r["detection_before"], r["detection_after"]
        mock = bool(b["metadata"].get("mock"))

        def val(d: dict, k: str):
            # Mock scores are synthetic; they never populate watermark columns.
            return None if mock else d[k]

        rows.append({
            "experiment_id": r["id"],
            "transformation": r["name"],
            "strength": r["strength"]["strength"],
            "words_changed": r["metrics"]["changed_words"],
            "chars_changed": r["metrics"]["changed_characters"],
            "edit_distance": r["metrics"]["edit_distance"],
            "tfidf_similarity": r["similarity"]["tfidf_cosine"],
            "char_ngram_similarity": r["similarity"]["char_3gram_cosine"],
            "preservation_score": r["preservation_score"],
            "watermark_score_before": val(b, "score"),
            "watermark_score_after": val(a, "score"),
            "p_value_before": val(b, "p_value"),
            "p_value_after": val(a, "p_value"),
            "detected_before": val(b, "detected"),
            "detected_after": val(a, "detected"),
            "detection_status_before": b["status"],
            "detection_status_after": a["status"],
            "detector": b["detector_name"],
            "detector_is_mock": mock,
        })
    return rows


def write_outputs(exp: dict[str, Any], out_dir: str | Path, plots: bool = True, report: bool = True) -> dict[str, str]:
    out = Path(out_dir)
    (out / "texts").mkdir(parents=True, exist_ok=True)
    (out / "audit").mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    slim = json.loads(json.dumps(exp))
    for r in slim["experiments"]:
        tp = out / "texts" / f"{r['id']}_{r['name']}.txt"
        tp.write_text(r.pop("output_text"), encoding="utf-8")
        ap = out / "audit" / f"{r['id']}_{r['name']}.json"
        ap.write_text(json.dumps(r.pop("audit_log"), indent=2, ensure_ascii=False), encoding="utf-8")
        r["output_file"] = str(tp.relative_to(out))
        r["audit_file"] = str(ap.relative_to(out))
    (out / "experiment.json").write_text(json.dumps(slim, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "baseline.json").write_text(json.dumps(exp["baseline"], indent=2, ensure_ascii=False), encoding="utf-8")
    written["experiment.json"] = str(out / "experiment.json")
    written["baseline.json"] = str(out / "baseline.json")
    with open(out / "experiment.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for row in csv_rows(exp):
            w.writerow({k: ("null" if v is None else v) for k, v in row.items()})
    written["experiment.csv"] = str(out / "experiment.csv")
    plot_paths: dict[str, str] = {}
    if plots:
        from .plots import make_plots
        plot_paths = make_plots(exp, out)
        written.update(plot_paths)
    if report:
        from .report import write_report
        written["report.html"] = str(write_report(exp, out / "report.html", plot_paths))
    return written
