"""Static audience classifier — returns a fixed group from config.

Placeholder until a real classifier (e.g. age estimation, mood detection) is
wired up. Lets us exercise the full pipeline end-to-end with deterministic
audience data.
"""
from __future__ import annotations

from audience.base import AudienceClassifier


class StaticAudienceClassifier(AudienceClassifier):
    def __init__(self, *, group: str):
        self._group = group

    def classify(self) -> dict:
        return {"group": self._group, "source": "static-config"}
