"""Pipeline context envelope.

The pipeline passes plain dicts between stages so future signals can be added
without touching the contract. :class:`PipelineContext` is just a typed
builder — it serialises to a dict via :meth:`to_dict` and every stage operates
on that dict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineContext:
    trigger: dict           # {"type": "person"|"timer", "reason": "...", "ts": iso8601}
    audience: dict = field(default_factory=dict)
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        # Top-level keys: trigger, audience, plus anything in extras.
        # extras wins if it collides — explicit override is intentional.
        return {
            "trigger": self.trigger,
            "audience": self.audience,
            **self.extras,
        }
