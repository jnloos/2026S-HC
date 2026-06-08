"""ContentSink — terminal stage of the pipeline.

The sink takes a selector result + the context that produced it and pushes
both somewhere (typically the Web UI). It must also be able to surface
pipeline errors so the UI doesn't go silent on a bad cycle.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ContentSink(ABC):
    @abstractmethod
    def publish(self, result: dict, context: dict) -> None: ...

    @abstractmethod
    def publish_error(self, message: str, *, context: dict) -> None: ...
