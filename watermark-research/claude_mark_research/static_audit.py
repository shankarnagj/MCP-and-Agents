"""Static zero-AI audit of the repository.

Searches every source/doc file for AI/LLM-related terms. A hit FAILS the
audit only if it is an import (Python ``import``/``from``) of a forbidden
module or a forbidden package in a dependency manifest. Other mentions
(documentation, test fixtures, CLI naming, this audit's own term list) are
listed as references for human review.
"""

from __future__ import annotations

import re
from pathlib import Path

TERMS = ["anthropic", "claude", "openai", "transformers", "torch", "tensorflow",
         "sentence_transformers", "ollama", "langchain", "llama", "qwen", "gemini"]
FORBIDDEN_MODULES = {"anthropic", "openai", "transformers", "torch", "tensorflow", "sentence_transformers",
                     "ollama", "langchain", "langchain_core", "langchain_openai", "llama_cpp", "llama_index",
                     "qwen", "google.generativeai", "google.genai", "huggingface_hub", "mistralai",
                     "cohere", "vllm", "keras", "jax", "flax", "spacy", "sklearn", "gensim"}
_IMPORT_RE = re.compile(r"^[ \t]*(?:from[ \t]+([\w.]+)[ \t]+import|import[ \t]+([\w., \t]+))", re.M)
_TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".json", ".yaml", ".yml", ".html", ".sh"}
_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", "build", "dist"}
_DEP_FILES = {"requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"}


def _files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and not (set(p.relative_to(root).parts) & _SKIP_DIRS) and \
                (p.suffix in _TEXT_SUFFIXES or p.name in _DEP_FILES):
            yield p


def audit(root: str | Path) -> dict:
    root = Path(root)
    violations, references = [], []
    term_re = re.compile("|".join(TERMS), re.I)
    for p in _files(root):
        text = p.read_text(encoding="utf-8", errors="replace")
        rel = str(p.relative_to(root))
        if p.suffix == ".py":
            for m in _IMPORT_RE.finditer(text):
                mods = [m.group(1)] if m.group(1) else [x.strip().split(" ")[0] for x in m.group(2).split(",")]
                for mod in mods:
                    if any(mod == f or mod.startswith(f + ".") for f in FORBIDDEN_MODULES):
                        violations.append({"file": rel, "line": text.count("\n", 0, m.start()) + 1,
                                           "kind": "forbidden_import", "text": m.group().strip()})
        if p.name in _DEP_FILES:
            for i, line in enumerate(text.splitlines(), 1):
                name = re.split(r"[<>=!~\[;\s\"']", line.strip().strip("\"',"), maxsplit=1)[0].lower()
                if name.replace("-", "_") in {f.replace(".", "_") for f in FORBIDDEN_MODULES} | {"torch", "tensorflow"}:
                    violations.append({"file": rel, "line": i, "kind": "forbidden_dependency", "text": line.strip()})
        for i, line in enumerate(text.splitlines(), 1):
            for m in term_re.finditer(line):
                references.append({"file": rel, "line": i, "term": m.group().lower()})
    by_term: dict[str, int] = {}
    for r in references:
        by_term[r["term"]] = by_term.get(r["term"], 0) + 1
    return {"passed": not violations, "violations": violations, "reference_counts": by_term,
            "references": references,
            "policy": ("FAIL on imports of AI/ML inference libraries or such dependencies. Mentions in "
                       "documentation, test fixtures, CLI naming and the detector plug-in docs are allowed.")}
