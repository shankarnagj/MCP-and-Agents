"""Deterministic normalisation functions used by ingestion, search and entity resolution."""

from __future__ import annotations

import ipaddress
import re
import unicodedata

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^0-9a-z ]+")
_NON_DIGIT = re.compile(r"\D+")

# Legal-form suffixes stripped for organisation matching
_ORG_SUFFIXES = {
    "inc", "incorporated", "ltd", "limited", "llc", "plc", "corp", "corporation", "co", "company",
    "gmbh", "ag", "sa", "sarl", "bv", "nv", "pvt", "private", "pte", "srl", "oy", "ab", "kk", "holdings", "group",
}
_NAME_TITLES = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "madam", "mx"}
_ADDRESS_ABBREV = {
    "street": "st", "st.": "st", "road": "rd", "avenue": "ave", "av": "ave", "boulevard": "blvd", "drive": "dr",
    "lane": "ln", "court": "ct", "place": "pl", "square": "sq", "suite": "ste", "apartment": "apt", "north": "n",
    "south": "s", "east": "e", "west": "w", "highway": "hwy", "floor": "fl",
}


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def basic(text: str | None) -> str:
    if not text:
        return ""
    t = strip_accents(str(text)).lower()
    t = _NON_ALNUM.sub(" ", t)
    return _WS.sub(" ", t).strip()


def person_name(text: str | None) -> str:
    tokens = [t for t in basic(text).split() if t not in _NAME_TITLES]
    return " ".join(tokens)


def org_name(text: str | None) -> str:
    tokens = [t for t in basic((text or "").replace("&", " and ")).split() if t not in _ORG_SUFFIXES]
    return " ".join(tokens)


def email(text: str | None) -> str:
    if not text:
        return ""
    t = str(text).strip().lower()
    if "@" not in t:
        return ""
    local, _, domain = t.partition("@")
    local = local.split("+", 1)[0]  # sub-addressing
    if domain in {"gmail.com", "googlemail.com"}:
        local = local.replace(".", "")
    return f"{local}@{domain}"


def phone(text: str | None, default_cc: str = "1") -> str:
    """Digits-only E.164-like form. Deterministic; no external lookups."""
    if not text:
        return ""
    raw = str(text).strip()
    digits = _NON_DIGIT.sub("", raw)
    if not digits:
        return ""
    if raw.startswith("+"):
        return "+" + digits
    if raw.startswith("00"):
        return "+" + digits[2:]
    if len(digits) == 10:
        return f"+{default_cc}{digits}"
    return "+" + digits


def address(text: str | None) -> str:
    tokens = basic(text).split()
    return " ".join(_ADDRESS_ABBREV.get(t, t) for t in tokens)


def ip(text: str | None) -> str:
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(str(text).strip()))
    except ValueError:
        return ""


def domain(text: str | None) -> str:
    if not text:
        return ""
    t = str(text).strip().lower().rstrip(".")
    t = re.sub(r"^https?://", "", t).split("/", 1)[0]
    return t[4:] if t.startswith("www.") else t


def identifier(text: str | None) -> str:
    """Generic identifier: upper-case alphanumerics only (account numbers, device ids, IMO ...)."""
    if text is None:
        return ""
    return re.sub(r"[^0-9A-Za-z]", "", str(text)).upper()


def date(text: str | None) -> str:
    """ISO date (YYYY-MM-DD) from common unambiguous formats."""
    if not text:
        return ""
    t = str(text).strip()
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return ""


NORMALIZERS = {
    "email": email,
    "phone": phone,
    "ip": ip,
    "domain": domain,
    "name": person_name,
    "org_name": org_name,
    "address": address,
    "dob": date,
}


def normalize_identifier(kind: str, value: str | None) -> str:
    fn = NORMALIZERS.get(kind)
    if fn is not None:
        return fn(value)
    return identifier(value)
