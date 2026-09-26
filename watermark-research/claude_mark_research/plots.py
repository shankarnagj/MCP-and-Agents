"""Tradeoff plots (matplotlib only, Agg backend, no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Reference categorical palette (validated default), light mode.
_SERIES_1 = "#2a78d6"
_SERIES_2 = "#eb6834"
_TEXT = "#0b0b0b"
_TEXT_2 = "#52514e"
_GRID = "#e4e3df"
_SURFACE = "#fcfcfb"


def _style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title, loc="left", fontsize=12, color=_TEXT, pad=12)
    ax.set_xlabel(xlabel, color=_TEXT_2)
    ax.set_ylabel(ylabel, color=_TEXT_2)
    ax.grid(True, color=_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(_GRID)
    ax.tick_params(colors=_TEXT_2)
    ax.set_facecolor(_SURFACE)


def _magnitude(r: dict[str, Any]) -> float:
    return r["strength"]["ratios"]["char_edit_ratio"]


def make_plots(exp: dict[str, Any], out_dir: str | Path) -> dict[str, str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # plots are optional
        return {}
    out = Path(out_dir)
    rows = exp["experiments"]
    xs = [_magnitude(r) for r in rows]
    paths: dict[str, str] = {}

    fig, ax = plt.subplots(figsize=(7.5, 4.6), dpi=130)
    fig.patch.set_facecolor(_SURFACE)
    ax.plot(xs, [r["preservation_score"] for r in rows], "o", color=_SERIES_1, markersize=8,
            markeredgecolor=_SURFACE, markeredgewidth=2, label="Preservation score")
    ax.plot(xs, [r["similarity"]["tfidf_cosine"] for r in rows], "s", color=_SERIES_2, markersize=7,
            markeredgecolor=_SURFACE, markeredgewidth=2, label="TF-IDF cosine")
    for x, r in zip(xs, rows):
        ax.annotate(r["id"], (x, r["preservation_score"]), textcoords="offset points", xytext=(6, 4),
                    fontsize=8, color=_TEXT_2)
    _style(ax, "Text preservation vs. transformation magnitude",
           "Character edit ratio (edit distance / characters)", "Lexical/structural similarity (0-1)")
    ax.set_ylim(min(0.0, ax.get_ylim()[0]), 1.05)
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout()
    p = out / "tradeoff_preservation.png"
    fig.savefig(p, facecolor=_SURFACE)
    plt.close(fig)
    paths["tradeoff_preservation.png"] = str(p)

    det = exp["detector"]
    have_scores = (not det.get("mock") and det.get("name") != "none"
                   and any(r["detection_after"]["score"] is not None for r in rows))
    if have_scores:
        fig, ax = plt.subplots(figsize=(7.5, 4.6), dpi=130)
        fig.patch.set_facecolor(_SURFACE)
        ys = [r["detection_after"]["score"] for r in rows]
        pts = [(x, y, r["id"]) for x, y, r in zip(xs, ys, rows) if y is not None]
        ax.plot([p_[0] for p_ in pts], [p_[1] for p_ in pts], "o", color=_SERIES_1, markersize=8,
                markeredgecolor=_SURFACE, markeredgewidth=2)
        for x, y, i in pts:
            ax.annotate(i, (x, y), textcoords="offset points", xytext=(6, 4), fontsize=8, color=_TEXT_2)
        thr = det.get("z_threshold")
        if thr is not None:
            ax.axhline(thr, color=_TEXT_2, linewidth=1, linestyle="--")
            ax.annotate(f"detection threshold ({thr})", (ax.get_xlim()[1], thr), ha="right", va="bottom",
                        fontsize=8, color=_TEXT_2)
        name = det.get("name", "detector")
        suffix = "" if det.get("authoritative") else " - testbed, not Claude"
        _style(ax, f"Detector score vs. transformation magnitude ({name}{suffix})",
               "Character edit ratio (edit distance / characters)", "Detector score")
        fig.tight_layout()
        p = out / "tradeoff_detector.png"
        fig.savefig(p, facecolor=_SURFACE)
        plt.close(fig)
        paths["tradeoff_detector.png"] = str(p)
    return paths
