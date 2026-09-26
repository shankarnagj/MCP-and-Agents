"""String similarity measures, implemented directly for transparency and auditability.

These are the classical, explainable algorithms; results are cross-checked against
reference libraries in the unit tests.
"""

from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def levenshtein_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return 1.0 - levenshtein(a, b) / max(len(a), len(b))


def jaro(a: str, b: str) -> float:
    if a == b:
        return 1.0 if a else 0.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    window = max(max(la, lb) // 2 - 1, 0)
    a_flags = [False] * la
    b_flags = [False] * lb
    matches = 0
    for i, ca in enumerate(a):
        lo, hi = max(0, i - window), min(i + window + 1, lb)
        for j in range(lo, hi):
            if not b_flags[j] and b[j] == ca:
                a_flags[i] = b_flags[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    transpositions = 0
    k = 0
    for i in range(la):
        if a_flags[i]:
            while not b_flags[k]:
                k += 1
            if a[i] != b[k]:
                transpositions += 1
            k += 1
    t = transpositions / 2
    return (matches / la + matches / lb + (matches - t) / matches) / 3


def jaro_winkler(a: str, b: str, prefix_scale: float = 0.1, max_prefix: int = 4) -> float:
    j = jaro(a, b)
    prefix = 0
    for ca, cb in zip(a[:max_prefix], b[:max_prefix]):
        if ca != cb:
            break
        prefix += 1
    return j + prefix * prefix_scale * (1 - j)


def token_overlap(a: str, b: str) -> float:
    """Jaccard similarity of whitespace tokens."""
    ta, tb = set(a.split()), set(b.split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def name_similarity(a: str, b: str) -> float:
    """Order-insensitive name similarity: best of direct and token-sorted Jaro-Winkler."""
    if not a or not b:
        return 0.0
    direct = jaro_winkler(a, b)
    sorted_a, sorted_b = " ".join(sorted(a.split())), " ".join(sorted(b.split()))
    return max(direct, jaro_winkler(sorted_a, sorted_b))
