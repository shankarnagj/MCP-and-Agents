import csv
import io
import json
import struct
import zlib

import pytest

from claude_mark_research.cli import main
from claude_mark_research.corpus import documents, long_prose, write_corpus
from claude_mark_research.experiment import EXPERIMENT_MATRIX, run_experiments, write_outputs
from claude_mark_research.interactive import run_interactive
from claude_mark_research.transforms.pipeline import Pipeline

KEY = "integration-key"


def _strip_time(exp):
    exp = json.loads(json.dumps(exp))
    exp["reproducibility"].pop("timestamp")
    return exp


def test_experiment_matrix_without_detector(tmp_path):
    exp = run_experiments(documents()["academic.md"])
    assert [r["id"] for r in exp["experiments"]] == list("ABCDEFGHIJ")
    assert exp["overall_detection_status"] == "UNKNOWN"
    written = write_outputs(exp, tmp_path, plots=True, report=True)
    rows = list(csv.DictReader(open(written["experiment.csv"])))
    assert len(rows) == 10
    for row in rows:
        for col in ("watermark_score_before", "watermark_score_after", "detected_before", "detected_after"):
            assert row[col] == "null"
        assert row["detection_status_after"] == "UNKNOWN"
    html = open(written["report.html"]).read()
    for label in ("VERIFIED FACT", "EXPERIMENTAL RESULT", "ASSUMPTION", "UNKNOWN", "DETECTION STATUS: UNKNOWN"):
        assert label in html
    for i in range(1, 11):
        assert f"<h2>{i}. " in html
    assert "removed" not in html.lower().replace("not proof of removal", "")


def test_mock_scores_never_populate_csv(tmp_path):
    from claude_mark_research.detector import build_detector
    exp = run_experiments(documents()["short_prose.txt"], build_detector("mock"))
    written = write_outputs(exp, tmp_path, plots=False, report=False)
    rows = list(csv.DictReader(open(written["experiment.csv"])))
    assert all(r["watermark_score_after"] == "null" and r["detector_is_mock"] == "True" for r in rows)


def test_reproducibility_same_input_same_output():
    text = long_prose(2)
    a = run_experiments(text)
    b = run_experiments(text)
    assert _strip_time(a) == _strip_time(b)
    for spec in ("conservative", "aggressive", "lexical-strong"):
        assert Pipeline(spec).run(text).output_text == Pipeline(spec).run(text).output_text


def test_seed_changes_hash_choices_but_is_stable():
    from claude_mark_research.transforms.pipeline import PipelineConfig
    text = long_prose(1)
    outs = {s: Pipeline("lexical-strong", PipelineConfig(seed=s)).run(text).output_text for s in (0, 1, 2)}
    assert len(set(outs.values())) > 1
    assert outs[1] == Pipeline("lexical-strong", PipelineConfig(seed=1)).run(text).output_text


def test_cli_end_to_end(tmp_path, capsys):
    corpus = tmp_path / "corpus"
    assert main(["corpus", "--out-dir", str(corpus)]) == 0
    src = corpus / "long_prose.txt"
    assert main(["analyze", str(src), "--out", str(tmp_path / "baseline.json")]) == 0
    assert json.loads((tmp_path / "baseline.json").read_text())["word_count"] > 100
    assert main(["unicode", str(corpus / "invisible_chars_control.txt"), "--strip-invisible",
                 "--out", str(tmp_path / "u.txt")]) == 0
    assert "​" not in (tmp_path / "u.txt").read_text()
    assert main(["transform", str(src), "--pipeline", "conservative", "--out", str(tmp_path / "t.txt")]) == 0
    audit = json.loads((tmp_path / "t.audit.json").read_text())
    assert audit["edits"] and audit["seed"] == 0 and "dictionary" in json.dumps(audit["pipeline"])
    # aggressive is refused without explicit confirmation
    assert main(["transform", str(src), "--pipeline", "aggressive", "--out", str(tmp_path / "a.txt")]) == 2
    assert main(["transform", str(src), "--pipeline", "aggressive", "--confirm-aggressive",
                 "--out", str(tmp_path / "a.txt")]) == 0
    assert main(["compare", str(src), str(tmp_path / "t.txt"), "--out", str(tmp_path / "cmp.json")]) == 0
    assert json.loads((tmp_path / "cmp.json").read_text())["detection_status"] == "UNKNOWN"
    out = tmp_path / "exp"
    assert main(["experiment", str(src), "--out-dir", str(out), "--toy-watermark", "--key", KEY,
                 "--detector", "local"]) == 0
    exp = json.loads((out / "experiment.json").read_text())
    by_id = {r["id"]: r for r in exp["experiments"]}
    assert by_id["A"]["detection_after"]["status"] == "DETECTED"
    for cid in "BCD":
        assert by_id[cid]["detection_after"]["score"] == by_id["A"]["detection_after"]["score"]
    assert (out / "tradeoff_detector.png").exists() and (out / "report.html").exists()
    assert main(["audit-static"]) == 0


def test_interactive_accept_reject():
    pipe = Pipeline("lexical")
    answers = iter(["y", "n", "q"])
    res = run_interactive(pipe, "Utilize this. Approximately two. Therefore three.",
                          input_fn=lambda _: next(answers), out=io.StringIO())
    assert res.output_text == "Use this. Approximately two. Therefore three."


def _png_with_chunk(ctype: bytes, body: bytes) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "blue").save(buf, "PNG")
    data = buf.getvalue()
    chunk = struct.pack(">I", len(body)) + ctype + body + struct.pack(">I", zlib.crc32(ctype + body))
    iend = data.rfind(b"IEND") - 4
    return data[:iend] + chunk + data[iend:]


def test_c2pa_absent_and_malformed(tmp_path):
    pytest.importorskip("PIL")
    from claude_mark_research.c2pa import C2PA_ABSENT, inspect_file
    p = tmp_path / "plain.png"
    p.write_bytes(_png_with_chunk(b"tEXt", b"Comment\x00hi"))
    r = inspect_file(p)
    assert r["status"] == C2PA_ABSENT and r["container"]["metadata"]["text_chunks"] == {"Comment": 10}
    # A malformed (unsigned, garbage) JUMBF box - never a valid credential.
    bad = tmp_path / "bad.png"
    bad.write_bytes(_png_with_chunk(b"caBX", b"\x00\x00\x00\x10jumbc2pa-garbage"))
    r = inspect_file(bad)
    assert r["status"] in ("C2PA_INVALID", "C2PA_UNVERIFIABLE")
    assert r["container"]["c2pa_bytes_found"]


def test_c2pa_classification_rules():
    from claude_mark_research.c2pa.report import classify
    scan = {"c2pa_bytes_found": True, "xmp_provenance_reference": False}
    assert classify(scan, {"sdk": None})[0] == "C2PA_UNVERIFIABLE"
    assert classify({**scan, "c2pa_bytes_found": False}, {"sdk": None})[0] == "C2PA_ABSENT"
    assert classify(scan, {"sdk": "x", "manifest_store": {}, "validation_state": "Valid"})[0] == "C2PA_PRESENT"
    assert classify(scan, {"sdk": "x", "manifest_store": {}, "validation_state": "Invalid"})[0] == "C2PA_INVALID"
    assert classify(scan, {"sdk": "x", "error": "e", "error_type": "C2paRemoteManifest"})[0] == "C2PA_UNVERIFIABLE"


def test_metadata_persistence_experiment(tmp_path):
    pytest.importorskip("PIL")
    from claude_mark_research.file_experiments import run
    src = tmp_path / "img.png"
    src.write_bytes(_png_with_chunk(b"tEXt", b"Author\x00someone"))
    res = run(src, tmp_path / "out")
    assert "metadata persistence" in res["label"]
    ops = {r["operation"]: r for r in res["experiments"]}
    assert ops["png_resave"]["metadata_before"]["text_chunks"] == {"Author": 14}
    assert ops["pixel_only_reencode (screenshot simulation)"]["metadata_after"]["text_chunks"] == {}
    assert all(r["C2PA_after"] == "C2PA_ABSENT" for r in res["experiments"])
