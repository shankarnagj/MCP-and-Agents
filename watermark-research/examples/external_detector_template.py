"""Template for plugging in an AUTHORISED watermark detector.

Use:
    claude-mark-research experiment input.txt --detector external \
        --detector-plugin examples/external_detector_template.py:AuthorisedDetector

Fill in `detect` with a call to a detector you are authorised to use (for
example, an official detection API once you have access to it). Do not
put reverse-engineered keys or guessed parameters here: results would be
meaningless and the report would present them as authoritative.
"""

from claude_mark_research.detector.base import DetectionResult


class AuthorisedDetector:
    def __init__(self, **options):
        self.options = options

    def detect(self, text: str) -> DetectionResult:
        raise NotImplementedError(
            "Connect this to an authorised detector. Return DetectionResult(detected, score, "
            "p_value, confidence, detector_name, metadata), or a dict with those keys."
        )
