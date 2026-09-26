import json
import sys
import textwrap

import pytest

from claude_mark_research.corpus import long_prose
from claude_mark_research.detector import build_detector
from claude_mark_research.detector.local_detector import LocalKeyedDetector
from claude_mark_research.toy_watermark import embed
from claude_mark_research.transforms.pipeline import Pipeline

KEY = b"test-research-key"


def test_none_detector_unknown():
    r = build_detector("none").detect("anything")
    assert r.status == "UNKNOWN" and r.score is None


def test_mock_is_flagged_and_unknown():
    r = build_detector("mock").detect("anything")
    assert r.is_mock and r.status == "UNKNOWN"
    assert build_detector("mock").detect("anything").score == r.score  # deterministic


def test_local_requires_key():
    with pytest.raises(ValueError):
        build_detector("local")


def test_toy_watermark_detected_only_with_right_key():
    marked, log = embed(long_prose(), KEY)
    assert log
    det = LocalKeyedDetector(KEY)
    assert det.detect(marked).status == "DETECTED"
    assert det.detect(long_prose()).status == "NOT_DETECTED"
    assert LocalKeyedDetector(b"other-key").detect(marked).status == "NOT_DETECTED"


def test_character_level_controls_do_not_change_token_signal():
    marked, _ = embed(long_prose(), KEY)
    noisy = marked.replace(" the ", " the​ ").replace("  ", " ")
    det = LocalKeyedDetector(KEY)
    base = det.detect(marked).score
    assert det.detect(noisy).score == base
    for spec in ("strip-invisible", "unicode-nfkc", "whitespace", "punctuation"):
        assert det.detect(Pipeline(spec).run(noisy).output_text).score == base


def test_short_text_insufficient():
    r = LocalKeyedDetector(KEY).detect("Too short.")
    assert r.detected is None and r.status == "UNKNOWN"


def test_external_plugin_and_command(tmp_path):
    plugin = tmp_path / "plug.py"
    plugin.write_text(textwrap.dedent("""
        class Det:
            def __init__(self, threshold="0.5"):
                self.t = float(threshold)
            def detect(self, text):
                return {"detected": len(text) > 3, "score": 0.9, "p_value": 0.01, "confidence": 0.99,
                        "detector_name": "fake-authorised"}
    """))
    d = build_detector("external", plugin=f"{plugin}:Det", options={"threshold": "0.7"})
    r = d.detect("hello")
    assert r.status == "DETECTED" and r.detector_name == "fake-authorised"
    script = tmp_path / "cmd.py"
    script.write_text("import sys, json; t=sys.stdin.read(); print(json.dumps({'detected': False, 'score': len(t)}))")
    d = build_detector("external", command=f"{sys.executable} {script}")
    r = d.detect("abcd")
    assert r.status == "NOT_DETECTED" and r.score == 4.0
    with pytest.raises(ValueError):
        build_detector("external")
