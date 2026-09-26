"""Pluggable watermark-detector interface.

No Claude/Anthropic detector is bundled. The official detector (and its
secret key) is not reproduced here. Users with authorised access can plug it
in through ``external_detector``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DetectionResult:
    detected: bool | None
    score: float | None
    p_value: float | None
    confidence: float | None
    detector_name: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_mock(self) -> bool:
        return bool(self.metadata.get("mock"))

    @property
    def status(self) -> str:
        """DETECTED / NOT_DETECTED / UNKNOWN. Mock output is always UNKNOWN
        because it carries no information about any real watermark."""
        if self.is_mock or self.detected is None:
            return "UNKNOWN"
        return "DETECTED" if self.detected else "NOT_DETECTED"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status
        return d

    @classmethod
    def from_mapping(cls, data: dict[str, Any], default_name: str) -> "DetectionResult":
        def num(key: str) -> float | None:
            v = data.get(key)
            return None if v is None else float(v)

        det = data.get("detected")
        return cls(
            detected=None if det is None else bool(det),
            score=num("score"), p_value=num("p_value"), confidence=num("confidence"),
            detector_name=str(data.get("detector_name") or default_name),
            metadata=dict(data.get("metadata") or {}),
        )


class WatermarkDetector:
    name = "base"
    #: True only for detectors backed by an authorised key/API for the target watermark.
    authoritative = False

    def detect(self, text: str) -> DetectionResult:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "authoritative": self.authoritative}


class NoDetector(WatermarkDetector):
    """Used when no detector is configured: every result is UNKNOWN."""

    name = "none"

    def detect(self, text: str) -> DetectionResult:
        return DetectionResult(None, None, None, None, self.name,
                               {"reason": "no detector configured; detection status is UNKNOWN"})
