import pytest

from app.ontology import load_ontology
from app.search.parser import QueryParseError, parse

O = load_ontology()
T, P = set(O.entity_types), O.all_property_names()


def test_exact_phrase():
    q = parse('"John Smith"', T, P)
    assert q.text_terms[0].mode == "exact" and q.text_terms[0].text == "John Smith"


def test_fuzzy_words_merge():
    q = parse("John Smith", T, P)
    assert len(q.text_terms) == 1 and q.text_terms[0].mode == "fuzzy" and q.text_terms[0].text == "John Smith"


def test_prefix_and_loose():
    q = parse("Joh* ~Smth", T, P)
    assert [t.mode for t in q.text_terms] == ["prefix", "loose"]


@pytest.mark.parametrize("query,alias,types", [
    ("account:12345", "account", ["Account"]), ("device:ABC123", "device", ["Device"]), ("ip:10.10.10.10", "ip", ["IPAddress"]),
    ("email:a@b.example", "email", []), ("domain:x.example", "domain", ["Domain"]),
])
def test_identifier_fields(query, alias, types):
    q = parse(query, T, P)
    assert q.identifiers[0].alias == alias
    assert q.include_types == types


def test_company_is_type_scoped_fuzzy():
    q = parse("company:Acme", T, P)
    assert q.include_types == ["Organization"] and q.text_terms[0].text == "Acme"


def test_type_filters_and_negation():
    q = parse("type:Person -type:Transaction", T, P)
    assert q.include_types == ["Person"] and q.exclude_types == ["Transaction"]


def test_date_geo_bbox_and_properties():
    q = parse('after:2026-01-01 before:2026-02-01 near:51.45,3.6,2km bbox:3,51,4,52 jurisdiction:"Castellan Isles"', T, P)
    assert q.date_from.isoformat().startswith("2026-01-01") and q.date_to.isoformat().startswith("2026-02-01")
    assert q.near == (51.45, 3.6, 2000.0)
    assert q.bbox == (3.0, 51.0, 4.0, 52.0)
    assert q.property_filters == [("jurisdiction", "Castellan Isles")]


def test_on_date_spans_one_day():
    q = parse("on:2026-02-14", T, P)
    assert (q.date_to - q.date_from).days == 1


@pytest.mark.parametrize("bad", ["type:Spaceship", "near:999,0,1km", "near:abc", "after:notadate", "x" * 600, " ".join(["a"] * 30)])
def test_errors(bad):
    with pytest.raises(QueryParseError):
        parse(bad, T, P)


def test_unknown_field_is_text_with_warning():
    q = parse("colour:blue", T, P)
    assert q.warnings and q.text_terms


def test_unbalanced_quotes_do_not_crash():
    q = parse('"John Smith', T, P)
    assert q.text_terms
