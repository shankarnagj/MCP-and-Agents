import json

import pytest

from app.ontology import Ontology, OntologyError, load_ontology


@pytest.fixture(scope="module")
def onto():
    return load_ontology()


def test_core_types_present(onto):
    for t in ["Person", "Organization", "Account", "Device", "Transaction", "Location", "Address", "IPAddress", "Domain", "Vehicle",
              "Shipment", "Vessel", "Event", "Document", "Case"]:
        assert t in onto.entity_types
    for r in ["OWNS", "WORKS_FOR", "CONTROLS", "TRANSFERRED_TO", "LOCATED_AT", "CONNECTED_TO", "COMMUNICATED_WITH", "VISITED",
              "TRANSACTED_WITH", "EMPLOYED_BY", "REGISTERED_AT", "ASSOCIATED_WITH", "DERIVED_FROM"]:
        assert r in onto.relationship_types


def test_relationship_validation(onto):
    onto.validate_relationship("OWNS", "Person", "Account")
    with pytest.raises(OntologyError):
        onto.validate_relationship("OWNS", "Transaction", "Account")
    with pytest.raises(OntologyError):
        onto.validate_relationship("NOT_A_TYPE", "Person", "Account")


def test_property_coercion_and_extras(onto):
    props = onto.validate_properties("Transaction", {"amount": "12.5", "channel": "card", "weird": 1, "status": ""})
    assert props["amount"] == 12.5
    assert props["_extra"] == {"weird": 1}
    assert "status" not in props
    with pytest.raises(OntologyError):
        onto.validate_properties("Transaction", {"amount": "abc"})
    with pytest.raises(OntologyError):
        onto.validate_properties("Transaction", {"weird": 1}, strict=True)


def test_sensitivity_and_identifiers(onto):
    assert onto.sensitivity("Person", "email") == "pii"
    assert onto.sensitivity("Person", "date_of_birth") == "restricted"
    assert onto.sensitivity("Device", "os") == "public"
    kinds = onto.identifier_kinds()
    assert ("Person", "email") in kinds["email"]
    assert ("IPAddress", "ip") in kinds["ip"]


def test_ontology_is_configurable(onto):
    data = json.loads(onto.model_dump_json())
    data["entity_types"]["Aircraft"] = {"label": "tail", "properties": {"tail": {"type": "string", "identifier": "tail", "searchable": True}}}
    data["relationship_types"]["OPERATES"] = {"source_types": ["Organization"], "target_types": ["Aircraft"]}
    new = Ontology.model_validate(data)
    new.validate_relationship("OPERATES", "Organization", "Aircraft")


@pytest.mark.parametrize("mutate", [
    lambda d: d["relationship_types"].update({"X": {"source_types": ["Nope"], "target_types": ["*"]}}),
    lambda d: d["entity_types"].update({"Bad": {"label": "missing", "properties": {"a": {}}}}),
    lambda d: d["entity_types"].update({"bad name!": {"label": "a", "properties": {"a": {}}}}),
])
def test_invalid_ontologies_rejected(onto, mutate):
    data = json.loads(onto.model_dump_json())
    mutate(data)
    with pytest.raises(ValueError):
        Ontology.model_validate(data)
