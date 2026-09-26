"""Detection of protected content that transformations must never modify.

Protected spans (URLs, code, numbers, citations, equations, ...) are found
with deterministic regular expressions. Transformations only ever edit the
*free* text between protected spans, so protected bytes stay byte-for-byte
identical unless the user explicitly disables a protection kind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)

# (kind, pattern). Order is priority: earlier kinds win on overlap.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("code_block", re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*\1[ \t]*$|\Z)", re.M | re.S)),
    ("equation", re.compile(r"\$\$.+?\$\$|\\\[.+?\\\]", re.S)),
    ("inline_code", re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)")),
    ("equation", re.compile(r"(?<![\\$\w])\$(?![\s$])[^$\n]+?(?<!\s)\$(?![\w$])|\\\(.+?\\\)")),
    ("markdown_link", re.compile(r"!?\[[^\]\n]*\]\([^)\s]+(?:\s+\"[^\"\n]*\")?\)")),
    ("url", re.compile(r"\b(?:https?|ftp)://[^\s<>()\[\]\"'`]+[^\s<>()\[\]\"'`.,;:!?]|\bwww\.[\w-]+(?:\.[\w-]+)+(?:/[^\s<>()\"'`]*[^\s<>()\"'`.,;:!?])?")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("citation", re.compile(
        r"\[\d+(?:\s*[,–-]\s*\d+)*\]"
        r"|\([A-Z][A-Za-z'-]+(?:\s+(?:et al\.|and|&)\s*(?:[A-Z][A-Za-z'-]+)?)?,?\s+\d{4}[a-z]?(?:,\s*p+\.\s*\d+(?:[–-]\d+)?)?\)"
    )),
    ("date", re.compile(
        r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
        r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
        rf"|\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b"
        rf"|\b\d{{1,2}}\s+(?:{_MONTHS})\.?\s+\d{{4}}\b"
    )),
    ("file_path", re.compile(
        r"(?<![\w/])(?:~|\.{1,2})?/(?:[\w.@-]+/)*[\w.@-]*[\w@-]/?"
        r"|\b[A-Za-z]:\\(?:[\w .-]+\\)*[\w .-]*"
        r"|\b[\w-]+(?:/[\w.-]+)+\.[A-Za-z0-9]{1,5}\b"
        r"|\b[\w-]+\.(?:py|js|ts|tsx|jsx|json|ya?ml|toml|ini|cfg|md|txt|csv|html?|css|sh|c|h|cpp|hpp|rs|go|java|rb|php|sql|xml|lock|log)\b"
    )),
    ("identifier", re.compile(
        r"\b[A-Za-z_][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b"           # snake_case / SCREAMING_CASE
        r"|\b[a-z]+(?:[A-Z][a-z0-9]*)+\b"                          # camelCase
        r"|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b"                  # PascalCase
        r"|\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\(\)"                  # call()
        r"|\b[a-z_][a-z0-9_]+(?:\.[a-z_][a-z0-9_]+)+\b(?!\s*$)"    # dotted.names
        r"|--?[a-z][\w-]*"                                         # CLI flags
    )),
    ("equation", re.compile(
        r"(?<![\w=])[A-Za-z]\w{0,3}\s*(?:=|<=|>=|<|>|≤|≥|≠)\s*[\w.()]+(?:\s*[-+*/^]\s*[\w.()]+)*"
    )),
    ("number", re.compile(r"(?<![\w.])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:%|st|nd|rd|th)?(?![\w])")),
]

# Interior of double-quoted spans (the quote marks themselves stay free).
_QUOTE_RE = re.compile(r"\"([^\"\n]{1,400})\"|“([^“”\n]{1,400})”")

CODE_KINDS = {"code_block", "inline_code"}
ALL_KINDS = {k for k, _ in _PATTERNS} | {"quote"}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str

    def overlaps(self, start: int, end: int) -> bool:
        return self.start < end and start < self.end


@dataclass
class ProtectionConfig:
    enabled: set[str] = field(default_factory=lambda: set(ALL_KINDS))

    @classmethod
    def build(cls, transform_code: bool = False, protect_quotes: bool = True,
              disable: list[str] | None = None) -> "ProtectionConfig":
        enabled = set(ALL_KINDS)
        if transform_code:
            enabled -= CODE_KINDS
        if not protect_quotes:
            enabled.discard("quote")
        for kind in disable or []:
            enabled.discard(kind)
        return cls(enabled)

    def to_dict(self) -> dict:
        return {"enabled": sorted(self.enabled)}


def find_protected(text: str, config: ProtectionConfig | None = None) -> list[Span]:
    config = config or ProtectionConfig()
    accepted: list[Span] = []

    def add(start: int, end: int, kind: str) -> None:
        if end <= start:
            return
        if any(s.overlaps(start, end) for s in accepted):
            return
        accepted.append(Span(start, end, kind))

    # Code is always located (so other patterns never match inside it), but is
    # only *protected* when enabled.
    code_spans: list[Span] = []
    for kind, pat in _PATTERNS:
        for m in pat.finditer(text):
            if kind in CODE_KINDS:
                if any(s.overlaps(m.start(), m.end()) for s in code_spans):
                    continue
                code_spans.append(Span(m.start(), m.end(), kind))
                if kind in config.enabled:
                    add(m.start(), m.end(), kind)
            elif kind in config.enabled:
                if any(s.overlaps(m.start(), m.end()) for s in code_spans):
                    continue
                add(m.start(), m.end(), kind)
    if "quote" in config.enabled:
        for m in _QUOTE_RE.finditer(text):
            g = 1 if m.group(1) is not None else 2
            s, e = m.start(g), m.end(g)
            if any(c.overlaps(s, e) for c in code_spans if c.kind in config.enabled):
                continue
            # Quote interiors may contain other protected items; keep them and
            # protect the rest of the interior around them.
            inner = sorted((sp for sp in accepted if sp.overlaps(s, e)), key=lambda sp: sp.start)
            pos = s
            for sp in inner:
                if sp.start > pos:
                    accepted.append(Span(pos, sp.start, "quote"))
                pos = max(pos, sp.end)
            if pos < e:
                accepted.append(Span(pos, e, "quote"))
    accepted.sort(key=lambda sp: sp.start)
    return accepted


def free_segments(text: str, spans: list[Span]) -> list[tuple[int, int]]:
    """Return (start, end) ranges of text not covered by any protected span."""
    out = []
    pos = 0
    for sp in spans:
        if sp.start > pos:
            out.append((pos, sp.start))
        pos = max(pos, sp.end)
    if pos < len(text):
        out.append((pos, len(text)))
    return out


def code_blocks(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, language) for every fenced code block."""
    out = []
    for m in _PATTERNS[0][1].finditer(text):
        header = m.group().lstrip().split("\n", 1)[0]
        lang = header.lstrip("`~").strip()
        out.append((m.start(), m.end(), lang))
    return out


_COMMENT_RE = re.compile(r"(?<![:\"'\w])(#|//|--(?=\s)|;;)[^\n]*|/\*.*?\*/|<!--.*?-->|\"\"\".*?\"\"\"", re.S)


def split_code_comments(code: str) -> tuple[str, str]:
    """Split code into (code_without_comments, comments) using language-agnostic
    comment syntax. Heuristic: string literals are not fully parsed."""
    comments = []

    def repl(m: re.Match[str]) -> str:
        comments.append(m.group())
        return " "

    stripped = _COMMENT_RE.sub(repl, code)
    return stripped, "\n".join(comments)
