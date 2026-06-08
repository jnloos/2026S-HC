"""Jinja2-based prompt rendering.

Prompts live as ``.j2`` files under ``app/templates/`` so they can be edited
without touching Python. Use :func:`render` from anywhere in the app.
"""
from __future__ import annotations

from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

_env = Environment(
    loader=PackageLoader("app", "templates"),
    autoescape=select_autoescape(default=False),  # prompts are plain text, not HTML
    undefined=StrictUndefined,  # missing vars should fail loud, not silently
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def render(template_name: str, /, **context: Any) -> str:
    """Render a template by name (relative to ``app/templates/``)."""
    return _env.get_template(template_name).render(**context)
