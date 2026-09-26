import time

import jwt
import pytest

from app.auth.rbac import ROLE_PERMISSIONS, has_permission
from app.auth.security import (
    create_access_token,
    decode_access_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    validate_password_policy,
    verify_password,
)
from app.config import Settings, get_settings
from app.privacy.masking import RESTRICTED_PLACEHOLDER, mask_label, mask_properties, mask_value
from app.ontology import load_ontology
from app.rules.engine import validate_rule_definition


def test_password_hashing():
    h = hash_password("Correct-Horse-9", rounds=4)
    assert verify_password("Correct-Horse-9", h) and not verify_password("wrong", h)
    long_pw = "x" * 100 + "A1!"
    assert not verify_password("x" * 100 + "B1!", hash_password(long_pw, rounds=4))  # >72 bytes still fully significant


@pytest.mark.parametrize("pw,ok", [("short1A!", False), ("alllowercaseletters", False), ("Longer-Passw0rd", True)])
def test_password_policy(pw, ok):
    if ok:
        validate_password_policy(pw)
    else:
        with pytest.raises(ValueError):
            validate_password_policy(pw)


def test_jwt_roundtrip_and_tamper():
    tok, _ = create_access_token("u1", "ANALYST", "s1")
    assert decode_access_token(tok)["sub"] == "u1"
    head, body, sig = tok.split(".")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(f"{head}.{body}.{sig[:-2]}AA")
    forged = jwt.encode({"sub": "u1", "sid": "s1", "exp": int(time.time()) + 60, "iss": "tessera"}, "not-the-key", algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(forged)
    none_alg = jwt.encode({"sub": "u1", "sid": "s1", "exp": int(time.time()) + 60, "iss": "tessera"}, None, algorithm="none")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(none_alg)
    expired = jwt.encode({"sub": "u1", "sid": "s1", "exp": int(time.time()) - 5, "iss": "tessera"}, get_settings().secret_key, algorithm="HS256")
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired)


def test_secret_encryption():
    token = encrypt_secret("postgresql://u:p@h/db")
    assert "p@h" not in token and decrypt_secret(token) == "postgresql://u:p@h/db"
    with pytest.raises(ValueError):
        decrypt_secret("garbage")


def test_production_rejects_dev_secrets():
    with pytest.raises(ValueError):
        Settings(env="production")
    Settings(env="production", secret_key="k" * 40, encryption_key="ZmFrZS1rZXktZm9yLXRlc3RzLTMyLWJ5dGVzLWxvbmch")


def test_rbac_matrix_is_monotonic():
    v, a, i, ad = (ROLE_PERMISSIONS[r] for r in ("VIEWER", "ANALYST", "INVESTIGATOR", "ADMIN"))
    assert v < a < i < ad
    assert not has_permission("VIEWER", "pii:view") and has_permission("ANALYST", "pii:view")
    assert not has_permission("ANALYST", "restricted:view") and has_permission("INVESTIGATOR", "restricted:view")
    assert not has_permission("INVESTIGATOR", "audit:read") and has_permission("ADMIN", "audit:read")
    assert not has_permission("NOBODY", "entity:read")


def test_masking_by_role():
    O = load_ontology()
    props = {"name": "Kalo Venri", "email": "kalo@example.com", "date_of_birth": "1980-01-01", "occupation": "clerk", "_extra": {"x": 1}}
    viewer, masked = mask_properties(O, "Person", props, "VIEWER")
    assert viewer["occupation"] == "clerk"
    assert viewer["email"] == "k***@example.com" and viewer["name"] != "Kalo Venri"
    assert viewer["date_of_birth"] == RESTRICTED_PLACEHOLDER
    assert "_extra" not in viewer and set(masked) >= {"email", "name", "date_of_birth", "_extra"}
    analyst, _ = mask_properties(O, "Person", props, "ANALYST")
    assert analyst["email"] == "kalo@example.com" and analyst["date_of_birth"] == RESTRICTED_PLACEHOLDER
    inv, masked_inv = mask_properties(O, "Person", props, "INVESTIGATOR")
    assert inv == props and masked_inv == []
    assert mask_label(O, "Person", "Kalo Venri", "VIEWER") == "K*** V****"
    assert mask_value("1234567890") == "••••••7890"


@pytest.mark.parametrize("name", ["Fraudulent device", "Money launderer detector", "guilty accounts"])
def test_rules_cannot_encode_verdicts(name):
    with pytest.raises(ValueError):
        validate_rule_definition("event", name, "", {"event_types": ["x"]})
