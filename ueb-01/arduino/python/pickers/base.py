"""ContentSelector — the *what* in the pipeline.

A selector takes a context dict and returns a chosen content dict:
``{"id", "name", "html", "description", "reasoning", "variant"}``.
Concrete implementations cover the three project variants — see
:mod:`pickers.edge` (V1), :mod:`pickers.hybrid` (V2), :mod:`pickers.cloud` (V3).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class SelectorError(RuntimeError):
    """Raised when a selector cannot produce a valid choice."""


class ContentSelector(ABC):
    @abstractmethod
    def select(self, context: dict) -> dict: ...


def result_from_cms(result: dict, variant: str) -> dict:
    """Build the selector result dict from a CMS ``choose-*`` response.

    Shared by the hybrid (V2) and cloud (V3) selectors — both let the CMS make
    the choice and just relabel its response with the variant tag. Mirrors the
    shape produced by :meth:`pickers.edge.EdgeSelector._to_result`.
    """
    return {
        "id": result["chosen_id"],
        "name": result.get("name", ""),
        "description": result.get("description", ""),
        "html": result.get("html", ""),
        "reasoning": result.get("reasoning", ""),
        "variant": variant,
    }
