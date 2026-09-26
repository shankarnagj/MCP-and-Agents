# claude-mark-research

A local, offline, **zero-AI** research tool for studying how robust a statistical text watermark (like the one Anthropic applies to Claude's output) is to **deterministic, non-generative** text transformations.

It measures how much each transformation changes a text, how much lexical and structural content survives, and, **only when you plug in a detector**, how the detector's score responds. It never claims a watermark was removed unless a detector you're authorised to use shows it.

## What this tool studies

**Statistical watermarking in text.** Anthropic says Claude's text watermark is a version of Google DeepMind's SynthID-Text. The watermark is applied while Claude chooses between words: it changes the source of randomness behind low-stakes word choices. Anthropic says nothing is added to the text and there are no hidden characters. Detection needs Anthropic's key, only estimates how likely it is that text was partly written by Claude, and works poorly on short samples ([Anthropic](https://www.anthropic.com/news/claude-text-watermark), [Help Center](https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content)).

Because the signal is in *which words* appear, this tool treats character-level cleanup as **control experiments**. That covers zero-width characters, Unicode forms, whitespace and quote styles. The tool shows that these controls leave the scored token sequence unchanged. Word-level transformations are the experiments proper: static synonym tables, phrase tables and narrowly matched sentence rules.

## What it does not do

It does **not**:

- recover, guess or approximate Anthropic's secret key
- reproduce Anthropic's proprietary detector, its parameters or thresholds
- guarantee removal of a Claude watermark, or claim removal without an authorised detector result
- prove authorship, or prove that text is human-written
- remove, alter or forge C2PA cryptographic provenance (the C2PA module is read-only)
- use AI to rewrite text: no LLMs, neural models, embeddings, paraphrasers or cloud AI APIs

The **Unknown** section of every report says so explicitly. Without an authorised detector the tool reports `DETECTION STATUS: UNKNOWN`.

## Install

```bash
cd watermark-research
pip install -e .                 # core: standard library only
pip install -e ".[all]"          # + matplotlib (plots), Pillow (image experiments), c2pa-python (C2PA verification), pytest
```

Python ≥ 3.10. The core has no third-party dependencies and makes no network calls.

## Quick start

```bash
claude-mark-research corpus --out-dir corpus                  # synthetic benchmark documents
claude-mark-research analyze corpus/long_prose.txt            # -> cmr-output/baseline.json
claude-mark-research unicode corpus/invisible_chars_control.txt --strip-invisible
claude-mark-research transform corpus/long_prose.txt --pipeline conservative
claude-mark-research transform corpus/long_prose.txt --pipeline aggressive --interactive
claude-mark-research experiment corpus/long_prose.txt --out-dir results          # no detector -> UNKNOWN
claude-mark-research experiment input.txt --detector external --detector-plugin my_det.py:Detector
claude-mark-research compare original.txt transformed.txt
claude-mark-research inspect-file image.png
claude-mark-research metadata-experiment image.png --out-dir meta
claude-mark-research audit-static
```

### Testbed: see a detector respond without any Claude access

`--toy-watermark` embeds a **synthetic** keyed lexical watermark with a key you choose. At each dictionary slot it picks the synonym that is "green" under HMAC(key, previous word). `--detector local` then runs a public green-list z-test with the same key. This lets you study the whole pipeline end to end on a token-choice signal. **It is not Claude's watermark, and its effect sizes do not transfer to Claude.**

```bash
claude-mark-research experiment corpus/long_prose.txt --out-dir results \
    --toy-watermark --key my-own-research-key --detector local
```

Example (synthetic corpus, seed 0). The z-score detection threshold is 4:

| ID | Transformation | Strength | Words changed | Preservation | Testbed z |
|----|---|---|---|---|---|
| A | original | NONE | 0 | 1.00 | 8.84 |
| B | Unicode normalization + strip invisible | LIGHT | 0 | 1.00 | 8.84 |
| C | whitespace | LIGHT | 0 | 1.00 | 8.84 |
| D | punctuation | LIGHT | 1 | 1.00 | 8.84 |
| E | lexical (light) | LIGHT | 71 | 0.99 | 5.99 |
| F | lexical (moderate) | MODERATE | 164 | 0.97 | 2.53 |
| G | lexical (strong) | STRONG | 318 | 0.91 | −1.13 |
| H | phrase | MODERATE | 90 | 0.98 | 8.76 |
| I | conservative | STRONG | 367 | 0.90 | 0.00 |
| J | aggressive | STRONG | 670 | 0.88 | −0.81 |

The character-level controls (B–D) leave the score exactly unchanged. Only word-choice changes move it, and they cost lexical similarity. This is a toy measurement, **not a statement about Claude**.

## Transformations

| Stage | Module | Notes |
|---|---|---|
| `unicode`, `unicode-nfc/nfkc/nfd/nfkd`, `strip-invisible` | `transforms/unicode_normalization.py` | Control ("Unicode normalization experiment") |
| `whitespace` | `transforms/whitespace.py` | collapses runs, trailing spaces, blank lines; keeps indentation |
| `punctuation` | `transforms/punctuation.py` | `--punctuation normalized|typographic|keep` |
| `lexical`, `lexical-light/moderate/strong` | `transforms/lexical_substitution.py` | `data/substitutions.json`, `--lexical-strategy first|hash|round_robin`, a/an agreement |
| `phrase` | `transforms/phrase_substitution.py` | `data/phrases.json` ("in order to" → "to") |
| `sentence` | `transforms/sentence_rules.py` | Rule A "X, because Y." → "Because Y, x."; Rule B restricted active → passive |
| `rewrite` | `transforms/deterministic_rewrite.py` | unambiguous contractions only |

Presets: `conservative` = unicode-nfc, whitespace, punctuation, phrase, lexical. `aggressive` = unicode-nfkc, whitespace, punctuation, phrase, sentence, lexical-strong, rewrite. Phrase and sentence rules run before single-word substitution so that their patterns are still intact when they run. Aggressive stages are **never applied silently**: `transform` refuses them unless you pass `--interactive` (approve or reject each edit) or `--confirm-aggressive`.

**Protected content** is never edited: fenced and inline code, URLs, e-mail addresses, numbers, dates, citations, Markdown links, file paths, code identifiers, equations and double-quoted text. Opt out with `--allow-code-transform` or `--no-protect-quotes`. Code blocks stay byte-for-byte identical.

**Strength** comes from measured edits, not intent. It is the highest level reached by three ratios: words changed / words, edit distance / characters, and rule-rewritten sentences / sentences. The defaults are LIGHT ≤ 5 %, MODERATE ≤ 20 % (sentences 10 % / 40 %). Override them with `--thresholds word_light=0.05,word_moderate=0.2,...`.

**Preservation** metrics are word overlap, TF-IDF cosine, character 3-gram cosine, sentence-length change, and preservation of named-entity strings, numbers, URLs and code blocks. They are reported as *lexical/structural similarity*, never as semantic equivalence.

## Detectors (`detector/`)

| `--detector` | What it is |
|---|---|
| `none` (default) | Every status is `UNKNOWN`; watermark fields are `null` |
| `mock` | Hash-based synthetic numbers to exercise the plumbing. Flagged `mock` and always `UNKNOWN`; never written to the CSV watermark columns |
| `local` | Keyed green-list z-test over word tokens with **your** key: the testbed detector. Cannot detect Claude's watermark |
| `external` | Your authorised detector: `--detector-plugin file.py:Class` (see `examples/external_detector_template.py`) or `--detector-cmd "cmd"` (text on stdin, JSON on stdout) |

## Outputs of `experiment`

`experiment.json` (full results plus reproducibility block), `experiment.csv` (tradeoff table; detector columns are `null` when unavailable), `baseline.json`, `texts/*.txt`, `audit/*.json` (one machine-readable entry per edit), `tradeoff_preservation.png`, `tradeoff_detector.png` (only with a real, non-mock detector), and `report.html`. The report has ten sections, and each claim is tagged VERIFIED FACT, EXPERIMENTAL RESULT, ASSUMPTION or UNKNOWN.

Every run records the seed, full configuration, component versions, dictionary version and sha256, input and output hashes, Python version and timestamp. The same input and configuration always give byte-identical outputs; the tests check this.

## C2PA (`c2pa/`)

`inspect-file` reads PNG and JPEG containers for JUMBF/C2PA boxes, EXIF, XMP and ICC. If `c2pa-python` is installed, it verifies manifests with the official SDK, with remote-manifest and OCSP fetching **disabled**. Each file gets one status: `C2PA_PRESENT`, `C2PA_ABSENT`, `C2PA_INVALID` or `C2PA_UNVERIFIABLE`. `metadata-experiment` re-saves and converts a copy (PNG↔JPEG, pixel-only re-encode as a screenshot simulation) and records metadata and C2PA status before and after. These are *metadata persistence experiments*. They say nothing about the text watermark. Nothing is ever signed or forged.

## Tests and audit

```bash
python -m pytest            # unit, integration, reproducibility, static-audit tests
claude-mark-research audit-static --root ..
```

The static audit fails on any import of an AI or ML inference library, or on any such dependency. Mentions of Claude or Anthropic in documentation, CLI naming and tests are listed for review but allowed.
