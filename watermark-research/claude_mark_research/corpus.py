"""Synthetic benchmark corpus, generated locally and deterministically.

All documents are written from fixed templates in this file. They contain no
private data and were not produced by a language model at run time. Content
is fictional; names and figures are invented for testing.
"""

from __future__ import annotations

from pathlib import Path

SHORT_PROSE = (
    "The committee will commence the review approximately two weeks after the deadline. "
    "Members should utilize the shared checklist in order to ensure that every submission "
    "is evaluated consistently. Subsequently, the chair will demonstrate the final ranking.\n"
)

_LONG_PARAS = [
    "The river town grew rapidly during the early decades, and numerous families settled near the "
    "old mill. Historians frequently indicate that the mill was the primary reason for this growth, "
    "because it provided steady work throughout the year. However, the records are incomplete, and "
    "additional sources are required to examine the question in detail.",
    "Visitors who attempt to walk the entire trail should obtain a map at the entrance. The route is "
    "difficult in places, and the signs are occasionally hard to read after heavy rain. Therefore, "
    "the park office recommends that individuals carry sufficient water and commence the hike early "
    "in the morning.",
    "The mill\u2019s owner \u2014 a careful man \u2014 kept \u201cexact\u201d ledgers\u2026  Few  of them survive ,  "
    "and the rest were lost!!\n"
    "It rained, because the front moved in from the west. The town council reviewed the proposal. "
    "The engineers measured the bridges. The volunteers collected the samples. The mayor approved "
    "this budget. We tested the pumps.",
    "In order to facilitate the restoration, the committee has the ability to purchase additional "
    "materials. Due to the fact that the budget is limited, it is important to note that the "
    "restoration will commence prior to the winter season. At this point in time, a large number "
    "of volunteers are able to assist with the work on a regular basis.",
    "The library typically lends various historical maps, and the staff frequently assist individuals "
    "who attempt to identify old property lines. Additionally, the archive contains significant "
    "collections of letters that demonstrate how the community changed. Consequently, researchers "
    "often utilize these components to construct an accurate timeline.",
]

FACTUAL = (
    "Water boils at 100 degrees Celsius at sea level (101.325 kPa). The Moon orbits Earth "
    "approximately every 27.3 days. Mount Everest is 8,849 metres tall according to the 2020 "
    "survey. The speed of light is about 299,792 km/s. Light takes approximately 8 minutes to "
    "reach Earth from the Sun. These values are frequently cited in introductory textbooks, "
    "and they are sufficient to demonstrate basic unit conversions.\n"
)

TECHNICAL = (
    "## Deployment notes\n\n"
    "To deploy the service, run `make deploy` from the repository root. The configuration file "
    "lives at /etc/example/service.yaml and the log file at ~/logs/service.log. The function "
    "load_config() reads the environment variable SERVICE_PORT, which defaults to 8080. See "
    "https://example.org/docs/deploy for details or email ops@example.org.\n\n"
    "The retry loop will terminate after 5 attempts. Numerous operators prefer to modify the "
    "backoff so that it will increase more rapidly, because the upstream API occasionally "
    "requires additional time to recover. Subsequently, the health check will indicate "
    "whether the service is ready. Use --dry-run to evaluate a change without applying it.\n"
)

ACADEMIC = (
    "# Effects of Shade on Seedling Growth\n\n"
    "Previous studies demonstrate that light availability is a primary determinant of seedling "
    "growth (Smith et al., 2019). However, numerous field experiments indicate that the effect "
    "varies across species [3, 4]. In order to examine this relationship, we utilized a randomized "
    "block design with 48 plots. The growth rate was modeled as r = a + b*L, where L denotes "
    "relative light. The results indicate a significant association (p < 0.01). Therefore, "
    "shade tolerance should be evaluated when individuals construct planting plans. As Jones "
    "wrote, \"shade is the forest's quiet architect\" (Jones, 2021).\n"
)

BULLETS = (
    "Checklist for the field visit:\n\n"
    "- Obtain approximately 20 sample bags before departure.\n"
    "- Utilize the GPS unit to identify each plot.\n"
    "- Additionally, record the temperature at 09:00 and 15:00.\n"
    "  - Nested item: examine the soil moisture.\n"
    "* Subsequently, upload the notes to the shared folder.\n"
    "1. Demonstrate the calibration step.\n"
    "2. Terminate the session once all plots are complete.\n"
)

MARKDOWN = (
    "# Project README\n\n"
    "This project is a **simple** tool that can facilitate numerous tasks. It is *frequently* "
    "used in order to obtain summaries of log files.\n\n"
    "> Note: Users should ensure that the input is sufficient before they commence.\n\n"
    "| Option | Meaning |\n|---|---|\n| `--fast` | Utilize the rapid mode |\n| `--safe` | Additional checks |\n\n"
    "See the [installation guide](https://example.org/install) for additional details.\n"
)

CODE = (
    "```python\n"
    "def utilize_cache(approximately, items):\n"
    "    # Subsequently demonstrate the result; therefore we utilize a dict.\n"
    "    cache = {}\n"
    "    for item in items:\n"
    "        cache[item] = approximately * 2  # numerous values\n"
    "    return cache\n"
    "\n"
    "print(\"hello\")\n"
    "```\n"
)

MIXED = (
    "The helper below will demonstrate how to utilize a cache. It is approximately ten lines "
    "long, and it is sufficient for numerous small scripts.\n\n"
    + CODE +
    "\nAfter running it, examine the output. The function `utilize_cache` requires two arguments; "
    "however, the first argument is frequently a constant. In order to modify the behaviour, "
    "edit config/settings.json and set max_items to 500.\n"
)


_NOUNS = ["committee", "survey team", "river crew", "archive staff", "field unit", "panel", "lab group",
          "county office", "school board", "harbor crew", "museum team", "library staff", "census team",
          "road crew", "water board", "garden club", "rail office", "clinic staff"]
_ADVS = ["frequently", "rapidly", "occasionally", "typically", "subsequently", "initially", "commonly",
         "significantly", "consequently", "additionally", "therefore", "approximately"]
_VERBS = ["demonstrated", "examined", "evaluated", "identified", "modified", "obtained", "constructed",
          "indicated", "required", "facilitated", "assisted", "attempted"]
_VERBS_BASE = ["demonstrate", "examine", "evaluate", "identify", "modify", "obtain", "construct",
               "indicate", "require", "facilitate", "assist", "attempt", "utilize", "commence"]
_ADJS = ["significant", "numerous", "additional", "sufficient", "accurate", "difficult", "simple",
         "entire", "various", "important", "primary", "initial", "large"]
_OBJS = ["records", "samples", "maps", "ledgers", "bridges", "budgets", "surveys", "reports", "pumps",
         "fences", "roads", "gardens", "wells", "letters"]
_TEMPLATES = [
    "The {n} {adv} {v} the {adj} {o}.",
    "Historians {adv} {v} that {adj} {o} were {adj2}.",
    "Each {n} will {vb} {adj} {o} before the season ends.",
    "In order to {vb} the {o}, the {n} {adv} {v} {adj} {o2}.",
    "It is clear that the {n} {v} these {o}, because the {o2} were {adj2}.",
    "The {n} reviewed the {o2}.",
]


def _generated_paragraphs(n_sentences: int) -> list[str]:
    """Deterministic template expansion with varied fillers, so that word
    contexts rarely repeat (important for token-level statistics)."""
    sents = []
    for i in range(n_sentences):
        t = _TEMPLATES[i % len(_TEMPLATES)]
        s = t.format(
            n=_NOUNS[(i * 7) % len(_NOUNS)], adv=_ADVS[(i * 5 + i // 7) % len(_ADVS)],
            v=_VERBS[(i * 3 + i // 11) % len(_VERBS)], vb=_VERBS_BASE[(i * 5 + 1) % len(_VERBS_BASE)],
            adj=_ADJS[(i * 4 + i // 13) % len(_ADJS)], adj2=_ADJS[(i * 9 + 5) % len(_ADJS)],
            o=_OBJS[(i * 3) % len(_OBJS)], o2=_OBJS[(i * 5 + 2) % len(_OBJS)],
        )
        s = s[0].upper() + s[1:]
        sents.append(s)
    return [" ".join(sents[i:i + 6]) for i in range(0, len(sents), 6)]


def long_prose(repeats: int = 4) -> str:
    """Hand-written paragraphs followed by 30*repeats template sentences."""
    return "\n\n".join(_LONG_PARAS + _generated_paragraphs(30 * repeats)) + "\n"


def documents() -> dict[str, str]:
    return {
        "short_prose.txt": SHORT_PROSE,
        "long_prose.txt": long_prose(),
        "factual.txt": FACTUAL,
        "technical.md": TECHNICAL,
        "academic.md": ACADEMIC,
        "bullet_list.md": BULLETS,
        "markdown.md": MARKDOWN,
        "code.md": CODE,
        "mixed_prose_code.md": MIXED,
        # Control: prose with injected invisible characters (NOT a watermark).
        "invisible_chars_control.txt": SHORT_PROSE.replace("review", "re​view")
                                                   .replace("checklist", "check‍list")
                                                   .replace("chair", "chаir") + "⁠",
    }


def write_corpus(out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in documents().items():
        p = out / name
        p.write_text(text, encoding="utf-8")
        paths.append(p)
    return paths
