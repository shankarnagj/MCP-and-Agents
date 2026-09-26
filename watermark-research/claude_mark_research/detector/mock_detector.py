"""Mock detector for development and testing ONLY.

It returns a deterministic pseudo-score derived from a hash of the text so
that the experiment plumbing (JSON, CSV, plots, report) can be exercised.
The numbers are synthetic and carry NO information about any watermark;
every result is flagged ``mock`` and reported with status UNKNOWN.
"""

from __future__ import annotations

import hashlib

from .base import DetectionResult, WatermarkDetector


class MockDetector(WatermarkDetector):
    name = "mock"

    def detect(self, text: str) -> DetectionResult:
        h = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        score = round(h / 2**64, 6)
        return DetectionResult(
            detected=score >= 0.5, score=score, p_value=round(1.0 - score, 6), confidence=None,
            detector_name=self.name,
            metadata={"mock": True,
                      "warning": "MOCK DETECTOR - synthetic output, NOT evidence about any watermark"},
        )

    def describe(self):
        return {**super().describe(), "mock": True}
