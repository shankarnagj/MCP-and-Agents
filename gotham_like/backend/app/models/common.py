from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class EpistemicStatus(str, enum.Enum):
    """How the platform knows something. Never collapse these categories.

    RAW                 – an unmodified source record
    DERIVED             – deterministically normalised/extracted from raw data
    ANALYST_ASSERTION   – an explicit claim made by a human analyst (a hypothesis)
    SYSTEM_INFERENCE    – produced by an algorithm (entity resolution, rules, analytics)
    VERIFIED            – a derived fact an authorised human has explicitly verified
    """

    RAW = "RAW"
    DERIVED = "DERIVED"
    ANALYST_ASSERTION = "ANALYST_ASSERTION"
    SYSTEM_INFERENCE = "SYSTEM_INFERENCE"
    VERIFIED = "VERIFIED"


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    INVESTIGATOR = "INVESTIGATOR"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class ResolutionDecision(str, enum.Enum):
    MATCH = "MATCH"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    NO_MATCH = "NO_MATCH"


class AssertionStatus(str, enum.Enum):
    HYPOTHESIS = "HYPOTHESIS"
    SUPPORTED = "SUPPORTED"  # analyst believes evidence supports it – still an assertion
    REFUTED = "REFUTED"
    WITHDRAWN = "WITHDRAWN"


class AlertStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ESCALATED = "ESCALATED"
    DISMISSED = "DISMISSED"


SYNTHETIC_LABEL = "SYNTHETIC / DEMONSTRATION DATA"
SIGNAL_LABEL = "ANALYTICAL SIGNAL"
