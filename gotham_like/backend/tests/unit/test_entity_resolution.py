import jellyfish
import pytest
from rapidfuzz.distance import Levenshtein as RFLev

from app.entity_resolution import normalize as N
from app.entity_resolution.resolver import blocking_keys, compare
from app.entity_resolution.similarity import jaro, jaro_winkler, levenshtein, levenshtein_similarity, name_similarity, token_overlap
from app.models import ResolutionDecision
from app.ontology import load_ontology

ONTO = load_ontology()
PAIRS = [("martha", "marhta"), ("dwayne", "duane"), ("dixon", "dicksonx"), ("", "abc"), ("abc", "abc"), ("kalo venri", "venri kalo"),
         ("jellyfish", "smellyfish"), ("a", "b")]


@pytest.mark.parametrize("a,b", PAIRS)
def test_jaro_winkler_matches_reference(a, b):
    assert jaro_winkler(a, b) == pytest.approx(jellyfish.jaro_winkler_similarity(a, b), abs=1e-9)
    assert jaro(a, b) == pytest.approx(jellyfish.jaro_similarity(a, b), abs=1e-9)


@pytest.mark.parametrize("a,b", PAIRS)
def test_levenshtein_matches_reference(a, b):
    assert levenshtein(a, b) == RFLev.distance(a, b)
    assert 0.0 <= levenshtein_similarity(a, b) <= 1.0


def test_token_overlap_and_name_similarity():
    assert token_overlap("a b c", "b c d") == pytest.approx(0.5)
    assert name_similarity("kalo venri", "venri kalo") == 1.0


@pytest.mark.parametrize("fn,inp,out", [
    (N.email, "  John.Doe+tag@Example.COM ", "john.doe@example.com"),
    (N.email, "j.o.h.n@gmail.com", "john@gmail.com"),
    (N.phone, "(202) 555 0671", "+12025550671"),
    (N.phone, "+1-202-555-0671", "+12025550671"),
    (N.phone, "0044 20 7946 0000", "+442079460000"),
    (N.person_name, "Dr. José  Álvarez", "jose alvarez"),
    (N.org_name, "Northwind Quartz Trading Ltd.", "northwind quartz trading"),
    (N.address, "12 Harbor Street", "12 harbor st"),
    (N.ip, "010.001.001.001", ""),
    (N.ip, "203.0.113.66", "203.0.113.66"),
    (N.domain, "https://www.Example.com/path", "example.com"),
    (N.identifier, "acc-000 12", "ACC00012"),
    (N.date, "1990/1/5", "1990-01-05"),
])
def test_normalizers(fn, inp, out):
    assert fn(inp) == out


def test_match_exposes_reasons():
    a = {"name": "Kalo Venri", "email": "kalo@example.com", "phone": "+1-202-555-0101", "date_of_birth": "1980-01-02"}
    b = {"name": "Dr Klao Venri", "email": "KALO@EXAMPLE.COM", "phone": "(202) 555 0101", "date_of_birth": "1980-01-02"}
    r = compare(ONTO, "Person", a, b)
    assert r.decision == ResolutionDecision.MATCH
    assert r.score >= 0.85
    reasons = r.reasons()
    assert "email exact match" in reasons and "phone exact match" in reasons
    assert any(x.startswith("name similarity: 0.9") for x in reasons)
    text = r.explain()
    assert text.startswith("MATCH SCORE: ") and "Evidence:" in text


def test_name_only_never_auto_merges():
    r = compare(ONTO, "Person", {"name": "Kalo Venri"}, {"name": "Kalo Venri"})
    assert r.decision == ResolutionDecision.POSSIBLE_MATCH


def test_dob_conflict_blocks_merge():
    a = {"name": "Kalo Venri", "phone": "+12025550101", "date_of_birth": "1980-01-02"}
    b = {"name": "Kalo Venri", "phone": "+12025550101", "date_of_birth": "1973-01-15"}
    r = compare(ONTO, "Person", a, b)
    assert r.decision == ResolutionDecision.POSSIBLE_MATCH
    assert "date_of_birth conflict" in r.conflicts


def test_different_people_no_match():
    r = compare(ONTO, "Person", {"name": "Kalo Venri", "email": "a@example.com"}, {"name": "Sumar Tidel", "email": "b@example.com"})
    assert r.decision == ResolutionDecision.NO_MATCH


def test_multi_valued_identifier_mismatch_not_counted():
    r = compare(ONTO, "Person", {"name": "Kalo Venri", "email": "a@example.com", "phone": "+12025550101"},
                {"name": "Kalo Venri", "email": "b@example.com", "phone": "+12025550101"})
    email = next(e for e in r.evidence if e.signal == "email")
    assert email.counted is False
    assert r.decision == ResolutionDecision.MATCH


def test_org_registration_conflict():
    r = compare(ONTO, "Organization", {"name": "Acme Holdings Ltd", "registration_number": "REG1"}, {"name": "ACME Holdings", "registration_number": "REG2"})
    assert r.decision != ResolutionDecision.MATCH


def test_blocking_keys_tolerate_order_and_format():
    k1 = blocking_keys(ONTO, "Person", {"name": "Kalo Venri", "email": "kalo@example.com"})
    k2 = blocking_keys(ONTO, "Person", {"name": "Venri Kalo", "email": "KALO@example.com"})
    assert k1 & k2


def test_evidence_never_contains_raw_values():
    """Evidence text is visible to roles that may not see the underlying fields (e.g. restricted DOB)."""
    a = {"name": "Kalo Venri", "email": "kalo@example.com", "phone": "+12025550101", "date_of_birth": "1980-01-02", "address": "12 Harbor Street"}
    b = {"name": "Kalo Venri", "email": "other@example.com", "phone": "+12025550199", "date_of_birth": "1973-01-15", "address": "9 Mill Road"}
    text = " ".join(compare(ONTO, "Person", a, b).reasons())
    for raw in ("1980", "1973", "kalo@", "other@", "2025550", "Harbor", "Mill"):
        assert raw not in text, raw
