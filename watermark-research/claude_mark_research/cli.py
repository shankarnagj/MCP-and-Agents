"""Command-line interface: ``claude-mark-research``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__

DEFAULT_OUT = "cmr-output"


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _dump(obj, path: str | Path | None) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
    else:
        print(text)


def _key(args) -> bytes | None:
    if getattr(args, "key_file", None):
        return Path(args.key_file).read_bytes().strip()
    if getattr(args, "key", None):
        return args.key.encode("utf-8")
    return None


def _add_transform_opts(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("transformation configuration")
    g.add_argument("--seed", type=int, default=0, help="seed for deterministic hash-based choices (default 0)")
    g.add_argument("--lexical-strategy", choices=["first", "hash", "round_robin"], default="hash")
    g.add_argument("--punctuation", choices=["normalized", "typographic", "keep"], default="normalized")
    g.add_argument("--unicode-form", choices=["NFC", "NFKC", "NFD", "NFKD"], default="NFKC")
    g.add_argument("--strip-invisible", action="store_true",
                   help="Unicode normalization experiment: also remove invisible characters (NOT watermark removal)")
    g.add_argument("--allow-code-transform", action="store_true",
                   help="allow edits inside code blocks and inline code (off by default)")
    g.add_argument("--no-protect-quotes", action="store_true", help="allow edits inside double-quoted text")
    g.add_argument("--substitutions", help="path to a custom substitutions.json")
    g.add_argument("--phrases", help="path to a custom phrases.json")
    g.add_argument("--rewrite-mode", choices=["expand", "contract"], default="expand")
    g.add_argument("--thresholds", help="strength thresholds, e.g. word_light=0.05,word_moderate=0.2")


def _add_detector_opts(p: argparse.ArgumentParser, default: str = "none") -> None:
    g = p.add_argument_group("detector")
    g.add_argument("--detector", choices=["none", "mock", "local", "external"], default=default,
                   help="none: status UNKNOWN; mock: synthetic dev output; local: keyed testbed detector "
                        "(NOT Claude); external: your authorised detector")
    g.add_argument("--detector-plugin", help="external: path/to/file.py:ClassName or module:ClassName")
    g.add_argument("--detector-cmd", help="external: command reading text on stdin, printing JSON")
    g.add_argument("--detector-option", action="append", default=[], metavar="K=V",
                   help="keyword argument for the plugin class (repeatable)")
    g.add_argument("--key", help="local testbed key (your own research key; never Anthropic's)")
    g.add_argument("--key-file", help="file containing the local testbed key")
    g.add_argument("--local-scope", choices=["lexical_slots", "all"], default="lexical_slots")
    g.add_argument("--gamma", type=float, default=0.5)
    g.add_argument("--z-threshold", type=float, default=4.0)


def _config(args):
    from .transforms.pipeline import PipelineConfig
    return PipelineConfig(seed=args.seed, lexical_strategy=args.lexical_strategy,
                          punctuation_mode=args.punctuation, unicode_form=args.unicode_form,
                          strip_invisible=args.strip_invisible, transform_code=args.allow_code_transform,
                          protect_quotes=not args.no_protect_quotes, substitutions_path=args.substitutions,
                          phrases_path=args.phrases, rewrite_mode=args.rewrite_mode)


def _detector(args):
    from .detector import build_detector
    opts = dict(o.split("=", 1) for o in args.detector_option)
    return build_detector(args.detector, key=_key(args), plugin=args.detector_plugin, command=args.detector_cmd,
                          options=opts, local_scope=args.local_scope, gamma=args.gamma,
                          z_threshold=args.z_threshold)


# --------------------------------------------------------------------------- commands

def cmd_analyze(args) -> int:
    from .baseline import analyze
    res = analyze(_read(args.input))
    out = args.out or str(Path(args.out_dir) / "baseline.json")
    _dump(res, out)
    print(f"words={res['word_count']} sentences={res['sentence_count']} paragraphs={res['paragraph_count']} "
          f"tokens={res['token_count']} TTR={res['lexical_diversity']['type_token_ratio']} "
          f"prose/code/comment tokens={res['code']['prose_tokens']}/{res['code']['code_tokens']}/"
          f"{res['code']['comment_tokens']}")
    print(f"wrote {out}")
    return 0


def cmd_unicode(args) -> int:
    from .transforms.pipeline import Pipeline, PipelineConfig
    from .unicode_diag import analyze_unicode
    text = _read(args.input)
    res = analyze_unicode(text)
    if args.json:
        _dump(res, None)
    else:
        print("Unicode diagnostic (character level)")
        print(f"  {res['disclaimer']}")
        print(f"  suspicious characters: {res['total_suspicious']} {res['counts']}")
        for f in res["findings"][:50]:
            extra = f" looks like {f['looks_like']!r}" if "looks_like" in f else ""
            print(f"  line {f['line']}:{f['column']}  {f['codepoint']}  {f['kind']:<20} {f['name']}{extra}")
        print(f"  normalization-stable: {res['normalization_forms_stable']}")
    if args.strip_invisible:
        pipe = Pipeline(["strip-invisible"] + ([f"unicode-{args.form.lower()}"] if args.form else []),
                        PipelineConfig())
        r = pipe.run(text)
        out = args.out or str(Path(args.out_dir) / "unicode_normalized.txt")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(r.output_text, encoding="utf-8")
        print(f"\nUnicode normalization experiment: {r.summary()['edit_count']} edits -> {out}")
        print("  This is NOT Claude watermark removal: that watermark is statistical (word choice), "
              "not hidden characters.")
    return 0


def cmd_transform(args) -> int:
    from .transforms.pipeline import Pipeline
    text = _read(args.input)
    pipe = Pipeline(args.pipeline, _config(args))
    if pipe.is_aggressive and not (args.interactive or args.confirm_aggressive):
        print("error: pipeline contains aggressive stages "
              f"({[n for n in pipe.stage_names if n in {'lexical-strong', 'sentence', 'rewrite'}]}). "
              "They are never applied silently: use --interactive to review each edit or "
              "--confirm-aggressive to accept them.", file=sys.stderr)
        return 2
    if args.interactive:
        from .interactive import run_interactive
        res = run_interactive(pipe, text)
    else:
        res = pipe.run(text)
    out = args.out or str(Path(args.out_dir) / "transformed.txt")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(res.output_text, encoding="utf-8")
    from .experiment import sha256
    from .strength import StrengthThresholds, classify
    from .textutil import sentences, words
    summ = res.summary()
    strength = classify(summ["changed_words"], len(words(text)), summ["edit_distance"], len(text),
                        summ["transformed_sentences"], len(sentences(text)), StrengthThresholds.parse(args.thresholds))
    from . import COMPONENT_VERSIONS
    audit = {"pipeline": pipe.describe(), "configuration": _config(args).to_dict(),
             "transformation_versions": COMPONENT_VERSIONS, "seed": args.seed,
             "input_sha256": sha256(text), "output_sha256": sha256(res.output_text),
             "summary": summ, "strength": strength, "edits": res.audit_log()}
    audit_path = args.audit or str(Path(out).with_suffix(".audit.json"))
    _dump(audit, audit_path)
    print(f"stages: {', '.join(pipe.stage_names)}")
    print(f"edits={summ['edit_count']} words_changed={summ['changed_words']} "
          f"edit_distance={summ['edit_distance']} strength={strength['strength']}")
    print(f"wrote {out}\nwrote {audit_path}")
    print("Note: text change alone says nothing about watermark detectability (status UNKNOWN without a detector).")
    return 0


def cmd_experiment(args) -> int:
    from .experiment import run_experiments, write_outputs
    from .strength import StrengthThresholds
    text = _read(args.input)
    extra = {}
    if args.toy_watermark:
        key = _key(args)
        if not key:
            print("error: --toy-watermark needs --key or --key-file", file=sys.stderr)
            return 2
        from .toy_watermark import embed
        text, log = embed(text, key, args.gamma)
        extra = {"toy_watermark": {"embedded": True, "edits": len(log),
                                   "note": "Synthetic testbed watermark applied before experiments. NOT Claude."}}
    det = _detector(args)
    exp = run_experiments(text, det, _config(args), StrengthThresholds.parse(args.thresholds),
                          source_name=args.input, extra_meta=extra)
    written = write_outputs(exp, args.out_dir, plots=not args.no_plots, report=not args.no_report)
    print(f"{'ID':<3} {'transformation':<28} {'strength':<9} {'words':>6} {'edit':>6} {'tfidf':>6} "
          f"{'pres':>6}  detection")
    for r in exp["experiments"]:
        a = r["detection_after"]
        score = "" if a["score"] is None or a["metadata"].get("mock") else f" score={a['score']}"
        print(f"{r['id']:<3} {r['name']:<28} {r['strength']['strength']:<9} {r['metrics']['changed_words']:>6} "
              f"{r['metrics']['edit_distance']:>6} {r['similarity']['tfidf_cosine']:>6} "
              f"{r['preservation_score']:>6}  {a['status']}{score}")
    print()
    print(exp["experiments"][-1]["interpretation"])
    for name, path in written.items():
        print(f"wrote {path}")
    return 0


def cmd_compare(args) -> int:
    from .similarity import compare
    from .strength import StrengthThresholds, classify
    from .textutil import anchored_edit_distance, changed_sentence_count, changed_word_count, sentences, words
    a, b = _read(args.original), _read(args.transformed)
    res = {"similarity": compare(a, b),
           "changed_words": changed_word_count(a, b), "changed_sentences": changed_sentence_count(a, b),
           "edit_distance": anchored_edit_distance(a, b)}
    res["strength"] = classify(res["changed_words"], len(words(a)), res["edit_distance"], len(a),
                               None, len(sentences(a)), StrengthThresholds.parse(args.thresholds))
    if args.detector != "none":
        det = _detector(args)
        res["detection_original"] = det.detect(a).to_dict()
        res["detection_transformed"] = det.detect(b).to_dict()
    else:
        res["detection_status"] = "UNKNOWN"
    _dump(res, args.out)
    if args.out:
        print(f"wrote {args.out}")
    return 0


def cmd_detect(args) -> int:
    det = _detector(args)
    _dump(det.detect(_read(args.input)).to_dict(), args.out)
    return 0


def cmd_inspect_file(args) -> int:
    from .c2pa.report import format_text, inspect_file
    res = inspect_file(args.path)
    if args.json:
        _dump(res, args.out)
    else:
        print(format_text(res))
        if args.out:
            _dump(res, args.out)
    return 0


def cmd_metadata_experiment(args) -> int:
    from .file_experiments import run
    res = run(args.path, args.out_dir)
    out = Path(args.out_dir) / "metadata_experiment.json"
    _dump(res, out)
    print(res["label"])
    for r in res["experiments"]:
        print(f"  {r['operation']:<45} C2PA {r['C2PA_before']} -> {r['C2PA_after']}")
    print(f"wrote {out}")
    return 0


def cmd_corpus(args) -> int:
    from .corpus import write_corpus
    for p in write_corpus(args.out_dir):
        print(p)
    return 0


def cmd_toy_embed(args) -> int:
    from .toy_watermark import embed
    key = _key(args)
    if not key:
        print("error: --key or --key-file required", file=sys.stderr)
        return 2
    text, log = embed(_read(args.input), key, args.gamma)
    out = args.out or str(Path(args.out_dir) / "toy_watermarked.txt")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(text, encoding="utf-8")
    _dump(log, str(Path(out).with_suffix(".audit.json")))
    print(f"Synthetic testbed watermark (NOT Claude's): {len(log)} keyed word choices -> {out}")
    return 0


def cmd_audit_static(args) -> int:
    from .static_audit import audit
    res = audit(args.root)
    print(f"Static AI audit of {args.root}: {'PASS' if res['passed'] else 'FAIL'}")
    for v in res["violations"]:
        print(f"  VIOLATION {v['file']}:{v['line']} {v['kind']}: {v['text']}")
    print(f"  term references (docs/naming/fixtures, reviewed separately): {res['reference_counts']}")
    if args.out:
        _dump(res, args.out)
    return 0 if res["passed"] else 1


# --------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="claude-mark-research",
        description="Zero-AI, deterministic research tool for measuring the robustness of statistical text "
                    "watermarks to non-generative transformations. It does not contain, recover or imitate "
                    "Anthropic's watermark key or detector.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("analyze", help="baseline statistics -> baseline.json")
    s.add_argument("input")
    s.add_argument("--out")
    s.add_argument("--out-dir", default=DEFAULT_OUT)
    s.set_defaults(func=cmd_analyze)

    s = sub.add_parser("unicode", aliases=["analyze-unicode"], help="Unicode diagnostic (hidden/invisible characters)")
    s.add_argument("input")
    s.add_argument("--json", action="store_true")
    s.add_argument("--strip-invisible", action="store_true", help="write a Unicode-normalized copy (control experiment)")
    s.add_argument("--form", choices=["NFC", "NFKC", "NFD", "NFKD"], default=None)
    s.add_argument("--out")
    s.add_argument("--out-dir", default=DEFAULT_OUT)
    s.set_defaults(func=cmd_unicode)

    s = sub.add_parser("transform", help="apply a deterministic pipeline")
    s.add_argument("input")
    s.add_argument("--pipeline", default="conservative",
                   help="comma-separated stages or preset: unicode, whitespace, punctuation, lexical, phrase, "
                        "sentence, rewrite, lexical-light|moderate|strong, unicode-nfc|nfkc|nfd|nfkd, "
                        "strip-invisible, conservative, aggressive")
    s.add_argument("--transform", dest="pipeline", help="alias of --pipeline (e.g. --transform unicode-nfc)")
    s.add_argument("--interactive", action="store_true", help="approve/reject each edit")
    s.add_argument("--confirm-aggressive", action="store_true", help="allow aggressive stages non-interactively")
    s.add_argument("--out")
    s.add_argument("--audit")
    s.add_argument("--out-dir", default=DEFAULT_OUT)
    _add_transform_opts(s)
    s.set_defaults(func=cmd_transform)

    s = sub.add_parser("experiment", help="run experiment matrix A-J -> experiment.json/csv, plots, report.html")
    s.add_argument("input")
    s.add_argument("--out-dir", default=DEFAULT_OUT)
    s.add_argument("--toy-watermark", action="store_true",
                   help="first embed the synthetic keyed testbed watermark (needs --key); pair with --detector local")
    s.add_argument("--no-plots", action="store_true")
    s.add_argument("--no-report", action="store_true")
    _add_transform_opts(s)
    _add_detector_opts(s)
    s.set_defaults(func=cmd_experiment)

    s = sub.add_parser("compare", help="compare two texts")
    s.add_argument("original")
    s.add_argument("transformed")
    s.add_argument("--out")
    s.add_argument("--thresholds")
    _add_detector_opts(s)
    s.set_defaults(func=cmd_compare)

    s = sub.add_parser("detect", help="run the configured detector on one text")
    s.add_argument("input")
    s.add_argument("--out")
    _add_detector_opts(s, default="mock")
    s.set_defaults(func=cmd_detect)

    s = sub.add_parser("inspect-file", help="inspect C2PA credentials and metadata of a file (read-only)")
    s.add_argument("path")
    s.add_argument("--json", action="store_true")
    s.add_argument("--out")
    s.set_defaults(func=cmd_inspect_file)

    s = sub.add_parser("metadata-experiment", help="metadata persistence experiment for an image file")
    s.add_argument("path")
    s.add_argument("--out-dir", default=DEFAULT_OUT)
    s.set_defaults(func=cmd_metadata_experiment)

    s = sub.add_parser("corpus", help="write the synthetic benchmark corpus")
    s.add_argument("--out-dir", default="corpus")
    s.set_defaults(func=cmd_corpus)

    s = sub.add_parser("toy-embed", help="embed the synthetic keyed testbed watermark (NOT Claude's)")
    s.add_argument("input")
    s.add_argument("--key")
    s.add_argument("--key-file")
    s.add_argument("--gamma", type=float, default=0.5)
    s.add_argument("--out")
    s.add_argument("--out-dir", default=DEFAULT_OUT)
    s.set_defaults(func=cmd_toy_embed)

    s = sub.add_parser("audit-static", help="static zero-AI audit of the source tree")
    s.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    s.add_argument("--out")
    s.set_defaults(func=cmd_audit_static)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
