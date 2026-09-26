"""Watermark detectors. See base.WatermarkDetector for the interface."""

from __future__ import annotations

from .base import DetectionResult, NoDetector, WatermarkDetector

DETECTOR_CHOICES = ("none", "mock", "local", "external")


def build_detector(kind: str, *, key: bytes | None = None, plugin: str | None = None,
                   command: str | None = None, options: dict | None = None,
                   local_scope: str = "lexical_slots", gamma: float = 0.5,
                   z_threshold: float = 4.0) -> WatermarkDetector:
    if kind == "none":
        return NoDetector()
    if kind == "mock":
        from .mock_detector import MockDetector
        return MockDetector()
    if kind == "local":
        from .local_detector import LocalKeyedDetector
        if not key:
            raise ValueError("--detector local requires --key or --key-file (your own research key)")
        return LocalKeyedDetector(key, gamma=gamma, scope=local_scope, z_threshold=z_threshold)
    if kind == "external":
        from .external_detector import ExternalDetector
        return ExternalDetector(plugin=plugin, command=command, options=options)
    raise ValueError(f"unknown detector {kind!r}; choose from {DETECTOR_CHOICES}")


__all__ = ["DetectionResult", "WatermarkDetector", "NoDetector", "build_detector", "DETECTOR_CHOICES"]
