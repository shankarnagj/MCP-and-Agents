"""claude-mark-research: a zero-AI, deterministic watermark-robustness research tool.

Nothing in this package performs model inference. Every transformation is a
static dictionary lookup, a regex rule or a Unicode/whitespace normalisation.
"""

__version__ = "0.1.0"

# Per-component versions recorded in every experiment for reproducibility.
COMPONENT_VERSIONS = {
    "tool": __version__,
    "tokenizer": "regex-1",
    "protect": "1.0",
    "unicode_normalization": "1.0",
    "whitespace": "1.0",
    "punctuation": "1.0",
    "lexical_substitution": "1.0",
    "phrase_substitution": "1.0",
    "sentence_rules": "1.0",
    "deterministic_rewrite": "1.0",
    "similarity": "1.0",
    "local_detector": "1.0",
}
