from pathlib import Path

from claude_mark_research.static_audit import audit

ROOT = Path(__file__).resolve().parent.parent


def test_repository_has_no_ai_imports():
    res = audit(ROOT)
    assert res["passed"], res["violations"]


def test_audit_catches_forbidden_import(tmp_path):
    (tmp_path / "bad.py").write_text("import torch\nfrom openai import OpenAI\nimport os, transformers\n")
    (tmp_path / "requirements.txt").write_text("sentence-transformers==2.0\nrequests\n")
    res = audit(tmp_path)
    assert not res["passed"]
    kinds = sorted(v["kind"] for v in res["violations"])
    assert kinds == ["forbidden_dependency", "forbidden_import", "forbidden_import", "forbidden_import"]
