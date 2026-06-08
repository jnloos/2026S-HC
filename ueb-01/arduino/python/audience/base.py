"""AudienceClassifier — estimates audience attributes from current sensor state.

Returns a JSON-serialisable dict (e.g. ``{"group": "young_adult", "confidence": 0.7}``).
Concrete implementations decide whether to consult the camera, the IMU, the
microphone, or a configured default.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class AudienceClassifier(ABC):
    @abstractmethod
    def classify(self) -> dict: ...
