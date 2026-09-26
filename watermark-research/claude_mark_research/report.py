"""Self-contained HTML research report (no external assets, no network)."""

from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Any

SOURCES = [
    ("Anthropic - How Claude's text watermarking works", "https://www.anthropic.com/news/claude-text-watermark"),
    ("Claude Help Center - How Claude marks AI-generated content",
     "https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content"),
    ("Dathathri et al., 'Scalable watermarking for identifying large language model outputs', Nature 634 (2024) - SynthID-Text",
     "https://www.nature.com/articles/s41586-024-08025-4"),
    ("Kirchenbauer et al., 'A Watermark for Large Language Models', ICML 2023", "https://arxiv.org/abs/2301.10226"),
]

CSS = """
:root{--bg:#fcfcfb;--fg:#0b0b0b;--fg2:#52514e;--line:#e4e3df;--card:#ffffff;
--fact:#1f6f3f;--exp:#2a78d6;--assume:#9a6400;--unknown:#8a3b8f}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1a1a19;--fg:#fff;--fg2:#c3c2b7;
--line:#3a3a37;--card:#232321;--fact:#5fc58a;--exp:#3987e5;--assume:#e0a93a;--unknown:#d58bd9}}
:root[data-theme="dark"]{--bg:#1a1a19;--fg:#fff;--fg2:#c3c2b7;--line:#3a3a37;--card:#232321;
--fact:#5fc58a;--exp:#3987e5;--assume:#e0a93a;--unknown:#d58bd9}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.7rem;margin:.2em 0}h2{margin-top:2.2em;border-bottom:1px solid var(--line);padding-bottom:.3em}
.muted{color:var(--fg2)}
.tag{display:inline-block;font-size:.72rem;font-weight:700;letter-spacing:.04em;padding:2px 7px;border-radius:4px;
border:1px solid currentColor;margin-right:.5em;vertical-align:1px}
.fact{color:var(--fact)}.exp{color:var(--exp)}.assume{color:var(--assume)}.unknown{color:var(--unknown)}
.claim{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:8px 0}
.claim p{margin:.2em 0}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.85rem;background:var(--card)}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top;white-space:nowrap}
th{color:var(--fg2);font-weight:600}
td.wrap{white-space:normal;min-width:220px}
img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:8px;background:#fcfcfb}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.85em}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px;overflow-x:auto;white-space:pre-wrap}
.status{font-weight:700;font-size:1.05rem}
"""

_TAGS = {"fact": "VERIFIED FACT", "exp": "EXPERIMENTAL RESULT", "assume": "ASSUMPTION", "unknown": "UNKNOWN"}


def _claim(kind: str, text: str) -> str:
    return f'<div class="claim"><p><span class="tag {kind}">{_TAGS[kind]}</span>{text}</p></div>'


def _img(path: str | None, alt: str) -> str:
    if not path or not Path(path).exists():
        return ""
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return f'<p><img alt="{html.escape(alt)}" src="data:image/png;base64,{data}"></p>'


def _fmt(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, float):
        return f"{v:.4g}"
    return html.escape(str(v))


def render(exp: dict[str, Any], plots: dict[str, str] | None = None) -> str:
    plots = plots or {}
    e = html.escape
    det = exp["detector"]
    rows = exp["experiments"]
    mock = bool(det.get("mock"))
    none = det.get("name") == "none"
    testbed = det.get("name") == "local-keyed-testbed"
    repro = exp["reproducibility"]
    base = exp["baseline"]

    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Watermark Robustness Report</title><style>{CSS}</style></head><body><main>"]
    parts.append("<h1>Watermark Robustness Report</h1>")
    parts.append(f"<p class='muted'>Source: <code>{e(exp['source'])}</code> &middot; input sha256 "
                 f"<code>{exp['input_sha256'][:16]}&hellip;</code> &middot; generated {e(repro['timestamp'])}</p>")

    # 1 Objective
    parts.append("<h2>1. Objective</h2>")
    parts.append(f"<p>{e(exp['research_question'])}</p><p>This report measures how much each deterministic, "
                 "non-generative transformation changes the text, how much lexical/structural content is "
                 "preserved, and - only where a detector is configured - how a detector's score responds.</p>")

    # 2 Threat / measurement model
    parts.append("<h2>2. Threat / measurement model</h2>")
    parts.append("<p>The transformer is a deterministic, offline process with no language model, no "
                 "paraphraser and no knowledge of any watermark key. It may only apply Unicode, whitespace "
                 "and punctuation normalisation, static dictionary substitutions, and narrowly-matched "
                 "sentence rules. Protected content (code, URLs, numbers, citations, equations, quoted "
                 "text) is never edited. The measured quantities are text change, similarity, and "
                 "detector response.</p>")
    parts.append(_claim("assume", "Classical similarity metrics (TF-IDF cosine, character n-grams, entity/number/URL "
                                  "preservation) are used as proxies for content preservation. They do not "
                                  "establish semantic equivalence; that requires human evaluation."))

    # 3 Background
    parts.append("<h2>3. Claude watermark background</h2>")
    parts.append(_claim("fact", "Anthropic states that Claude's text watermark is a version of the SynthID-Text "
                                "approach (Google DeepMind, Nature 2024), applied while Claude chooses between "
                                "words: it changes the source of randomness used for low-stakes word choices."))
    parts.append(_claim("fact", "Anthropic states that nothing is added to the text: no hidden characters. "
                                "Character-level diagnostics therefore do not find the watermark, and removing "
                                "invisible characters is a control experiment, not watermark removal."))
    parts.append(_claim("fact", "Anthropic states that detection requires its key, answers only how likely text "
                                "is to be partly Claude-written, does not prove human authorship, and works "
                                "poorly on short samples."))
    parts.append(_claim("unknown", "Claude's exact watermark parameters, key, scoring function, detection "
                                   "thresholds and token-level implementation are not public. This tool does "
                                   "not reproduce or approximate them."))

    # 4 Methodology
    parts.append("<h2>4. Experimental methodology</h2>")
    parts.append("<p>The input is transformed by each pipeline of the experiment matrix (A-J). For each output "
                 "the tool records the edit log, word/character/sentence change counts, character edit "
                 "distance, a measured strength class, and similarity metrics against the original. The "
                 "configured detector (if any) is run on the original and on every output.</p>")
    th = repro["strength_thresholds"]
    parts.append(f"<p>Strength is the highest level reached by any measured ratio: words changed / words "
                 f"(LIGHT &le; {th['word_light']}, MODERATE &le; {th['word_moderate']}), edit distance / characters "
                 f"(&le; {th['char_light']}, &le; {th['char_moderate']}), sentences restructured by sentence rules / sentences "
                 f"(&le; {th['sentence_light']}, &le; {th['sentence_moderate']}); above is STRONG.</p>")
    parts.append(f"<p>Detector: <code>{e(det.get('name', ''))}</code>. "
                 + ("No detector configured." if none else
                    "Mock detector: synthetic output used only to test plumbing." if mock else
                    "Local keyed <em>testbed</em> detector on a synthetic lexical watermark with a user-chosen key; it cannot detect Claude's watermark." if testbed else
                    "External detector supplied by the user; its authorisation and correctness are asserted by the user.")
                 + "</p>")

    # 5 Transformations
    parts.append("<h2>5. Transformations tested</h2><div class='table-wrap'><table><tr><th>ID</th><th>Name</th>"
                 "<th>Pipeline</th><th>Edits</th><th class='wrap'>Note</th></tr>")
    for r in rows:
        parts.append(f"<tr><td>{r['id']}</td><td>{e(r['name'])}</td><td>{e(', '.join(r['pipeline']) or '-')}</td>"
                     f"<td>{r['metrics']['edit_count']}</td><td class='wrap'>{e(r['note'])}</td></tr>")
    parts.append("</table></div>")

    # 6 Preservation
    parts.append("<h2>6. Text preservation</h2>")
    parts.append(f"<p class='muted'>Input: {base['word_count']} words, {base['sentence_count']} sentences, "
                 f"{base['character_count']} characters; prose/code/comment regex tokens: "
                 f"{base['code']['prose_tokens']}/{base['code']['code_tokens']}/{base['code']['comment_tokens']}.</p>")
    parts.append("<div class='table-wrap'><table><tr><th>ID</th><th>Strength</th><th>Words changed</th>"
                 "<th>Edit distance</th><th>Word ratio</th><th>Char ratio</th><th>Sentence ratio</th>"
                 "<th>TF-IDF cos</th><th>Char 3-gram cos</th><th>Numbers kept</th><th>URLs kept</th>"
                 "<th>Code kept</th><th>Preservation</th></tr>")
    for r in rows:
        s, m, sim = r["strength"], r["metrics"], r["similarity"]
        parts.append(
            f"<tr><td>{r['id']}</td><td>{s['strength']}</td><td>{m['changed_words']}</td><td>{m['edit_distance']}</td>"
            f"<td>{_fmt(s['ratios']['word_replacement_ratio'])}</td><td>{_fmt(s['ratios']['char_edit_ratio'])}</td>"
            f"<td>{_fmt(s['ratios']['sentence_transformation_ratio'])}</td><td>{_fmt(sim['tfidf_cosine'])}</td>"
            f"<td>{_fmt(sim['char_3gram_cosine'])}</td><td>{_fmt(sim['numbers']['ratio'])}</td>"
            f"<td>{_fmt(sim['urls']['ratio'])}</td><td>{_fmt(sim['code_blocks']['ratio'])}</td>"
            f"<td>{_fmt(r['preservation_score'])}</td></tr>")
    parts.append("</table></div>")
    parts.append(_claim("exp", "Values above are measured on this input with this configuration; they are "
                               "lexical/structural similarity, not semantic equivalence."))
    parts.append(_img(plots.get("tradeoff_preservation.png"), "Preservation vs. transformation magnitude"))

    # 7 Detector results
    parts.append("<h2>7. Detector results</h2>")
    if none or mock:
        parts.append("<p class='status'>DETECTION STATUS: UNKNOWN</p>")
        parts.append(_claim("unknown", "No authorised detector was available"
                            + (" (the mock detector's synthetic scores are excluded as evidence)" if mock else "")
                            + ". The watermark's detectability can only be evaluated if an authorised "
                              "detector is available. No claim is made about watermark removal."))
    else:
        parts.append("<div class='table-wrap'><table><tr><th>ID</th><th>Score before</th><th>Score after</th>"
                     "<th>p before</th><th>p after</th><th>Status before</th><th>Status after</th>"
                     "<th>Signal change</th><th class='wrap'>Interpretation</th></tr>")
        for r in rows:
            b, a = r["detection_before"], r["detection_after"]
            parts.append(f"<tr><td>{r['id']}</td><td>{_fmt(b['score'])}</td><td>{_fmt(a['score'])}</td>"
                         f"<td>{_fmt(b['p_value'])}</td><td>{_fmt(a['p_value'])}</td><td>{b['status']}</td>"
                         f"<td>{a['status']}</td><td>{_fmt(r['signal_change'])}</td>"
                         f"<td class='wrap'>{e(r['interpretation'])}</td></tr>")
        parts.append("</table></div>")
        if testbed:
            parts.append(_claim("exp", "These scores come from the local testbed detector on a synthetic "
                                       "dictionary-based watermark embedded with a user-chosen key. They show how "
                                       "each transformation disturbs a token-choice signal of that kind. They do "
                                       "not measure, and must not be reported as measuring, Claude's watermark."))
        else:
            parts.append(_claim("exp", "Scores come from the user-supplied external detector. A single "
                                       "below-threshold result is not proof of removal."))
        parts.append(_img(plots.get("tradeoff_detector.png"), "Detector score vs. transformation magnitude"))

    # 8 Limitations
    parts.append("<h2>8. Limitations</h2><ul>"
                 "<li>No access to Anthropic's detector or key; Claude-specific detectability is UNKNOWN without it.</li>"
                 "<li>Similarity metrics are lexical/structural; meaning drift from synonym substitution is not measured.</li>"
                 "<li>The static dictionary and sentence rules are small and conservative; coverage differs by genre.</li>"
                 "<li>The regex tokenizer differs from any model tokenizer; token counts are not model tokens.</li>"
                 "<li>Results come from one input and one seed; variance across texts needs a corpus run.</li>"
                 "<li>The local testbed watermark is a toy analogue; effect sizes do not transfer to SynthID-Text.</li></ul>")

    # 9 Interpretation
    parts.append("<h2>9. Interpretation</h2>")
    controls = [r for r in rows if r["id"] in ("B", "C", "D")]
    if not (none or mock) and controls and all(r["detection_after"]["score"] is not None for r in controls):
        same = all(r["detection_after"]["score"] == r["detection_before"]["score"] for r in controls)
        parts.append(_claim("exp", "Character-level controls (B, C, D): detector score "
                            + ("unchanged" if same else "changed") + " relative to the original."))
    else:
        parts.append(_claim("assume", "Unicode, whitespace and punctuation controls change characters but not "
                                      "the sequence of words; a word-choice watermark is not expected to depend "
                                      "on them. Untested here without a detector."))
    if none or mock:
        parts.append(_claim("unknown", "Whether any transformation changes the detectability of Claude's "
                                       "watermark is UNKNOWN: no authorised detector was run."))
    else:
        lost = [r["id"] for r in rows if r["detection_before"]["status"] == "DETECTED"
                and r["detection_after"]["status"] == "NOT_DETECTED"]
        kept = [r["id"] for r in rows if r["detection_after"]["status"] == "DETECTED"]
        parts.append(_claim("exp", f"Still detected after: {', '.join(kept) or 'none'}. Below threshold after: "
                                   f"{', '.join(lost) or 'none'}. "
                                   + ("Testbed detector only - not a statement about Claude." if testbed else "")))
    parts.append(_claim("assume", "Any below-threshold result should be weighed against the preservation cost "
                                  "shown in section 6; heavier edits trade away content similarity."))

    # 10 Reproducibility
    parts.append("<h2>10. Reproducibility information</h2>")
    import json as _json
    parts.append(f"<pre>{e(_json.dumps(repro, indent=2, ensure_ascii=False))}</pre>")
    parts.append("<h2>Sources</h2><ul>" + "".join(
        f"<li><a href='{u}'>{e(t)}</a></li>" for t, u in SOURCES) + "</ul>")
    parts.append("</main></body></html>")
    return "\n".join(parts)


def write_report(exp: dict[str, Any], path: str | Path, plots: dict[str, str] | None = None) -> Path:
    p = Path(path)
    p.write_text(render(exp, plots), encoding="utf-8")
    return p
