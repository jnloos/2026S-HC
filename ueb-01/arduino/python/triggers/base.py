"""TriggerStrategy — the *when* in the pipeline.

A trigger is an event source: ``start(on_fire)`` registers a callback that the
trigger invokes whenever conditions warrant a new content selection. The
callback receives an initial context dict carrying trigger metadata
(``{"type", "reason", "ts"}``).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

OnFire = Callable[[dict], None]


class TriggerStrategy(ABC):
    @abstractmethod
    def start(self, on_fire: OnFire) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
