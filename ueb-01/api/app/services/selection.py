"""Claude-backed content selection for the DigSig prototype.

Two entry points, mirroring the two non-trivial signage variants:

- :func:`choose_by_context` — text-only. Caller supplies an open-shaped
  ``context`` dict (audience, weather, anything else the client wants to
  send); the LLM picks one content from the pool.
- :func:`choose_by_image` — vision. Caller supplies an image plus optional
  context; the LLM recognises the scene/audience and picks one content.

The prompts themselves live as Jinja2 templates under ``app/templates/`` —
edit them there, not here. This module only wires data into the templates,
calls the API, and validates the response.

Uses Claude Haiku 4.5 (cheapest multimodal model with structured outputs).
"""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

import anthropic
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.debug import bus
from app.models import Content
from app.prompts import render
from app.services import contents as content_service

# Per-snippet character cap fed into the prompt. Selection rarely needs the
# full body; a short preview keeps token costs predictable on large pools.
SNIPPET_PREVIEW_CHARS = 2000

# Structured-output schema constraining Claude's JSON shape at the API level.
_CHOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "chosen_id": {"type": "integer"},
        "reasoning": {"type": "string"},
    },
    "required": ["chosen_id", "reasoning"],
    "additionalProperties": False,
}


class SelectionError(RuntimeError):
    """Raised when Claude selection cannot produce a valid choice."""


@dataclass(frozen=True)
class SelectionResult:
    chosen_id: int
    reasoning: str


class _ClaudeChoice(BaseModel):
    chosen_id: int
    reasoning: str


_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise SelectionError("ANTHROPIC_API_KEY is not configured")
        _client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.claude_timeout_seconds,
        )
    return _client


async def _candidates_for_prompt(contents: Sequence[Content]) -> list[dict]:
    """Build the list of candidate dicts the templates render over.

    The HTML can contain images that the text-mode LLM can't see, so the
    ``description`` field is the primary signal for selection.
    """
    items: list[dict] = []
    for c in contents:
        html = (await content_service.read_html(c)).strip()
        if len(html) > SNIPPET_PREVIEW_CHARS:
            html = html[:SNIPPET_PREVIEW_CHARS] + "…"
        items.append(
            {"id": c.id, "name": c.name, "description": c.description, "html": html}
        )
    return items


def _validate_choice(raw: str, valid_ids: set[int]) -> SelectionResult:
    try:
        data = json.loads(raw)
        choice = _ClaudeChoice.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise SelectionError(f"Claude returned malformed JSON: {raw!r}") from e
    if choice.chosen_id not in valid_ids:
        raise SelectionError(
            f"Claude picked id={choice.chosen_id} which is not in the pool {sorted(valid_ids)}"
        )
    return SelectionResult(chosen_id=choice.chosen_id, reasoning=choice.reasoning)


async def _post_chat(system: str, user_content: str | list[dict]) -> str:
    """Call Claude with the given system prompt + user content, return the JSON text body.

    ``user_content`` is a plain string for text-only requests, or a list of
    content blocks (e.g. image + text) for vision requests.
    """
    client = _get_client()
    try:
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            output_config={"format": {"type": "json_schema", "schema": _CHOICE_SCHEMA}},
        )
    except anthropic.APIStatusError as e:
        body = getattr(e, "message", str(e))
        raise SelectionError(f"Claude returned HTTP {e.status_code}: {body[:500]}") from e
    except anthropic.APIError as e:
        raise SelectionError(f"Claude request failed: {e}") from e

    for block in response.content:
        if block.type == "text":
            return block.text
    raise SelectionError("Claude returned no text content")


async def choose_by_context(
    pool_contents: Sequence[Content],
    *,
    context: dict | None,
) -> SelectionResult:
    """Pick a content based on an open-shaped context dict.

    ``context`` may contain anything the client wants the model to consider —
    typically ``{"audience": {...}, "weather": ..., ...}`` — but the dict is
    not validated; unknown keys flow straight into the prompt.
    """
    if not pool_contents:
        raise SelectionError("pool is empty — nothing to choose")

    candidates = await _candidates_for_prompt(pool_contents)
    system = render("selection_system.j2")
    user_msg = render("choose_by_context_user.j2", context=context, candidates=candidates)

    raw: str | None = None
    try:
        raw = await _post_chat(system, user_msg)
        result = _validate_choice(raw, {c.id for c in pool_contents if c.id is not None})
    except SelectionError as exc:
        _push_selection_event(
            variant="v2", system=system, user_prompt=user_msg, raw=raw, result=None, error=str(exc)
        )
        raise
    _push_selection_event(
        variant="v2", system=system, user_prompt=user_msg, raw=raw, result=result, error=None
    )
    return result


async def choose_by_image(
    pool_contents: Sequence[Content],
    *,
    image_bytes: bytes,
    mime_type: str,
    context: dict | None = None,
) -> SelectionResult:
    """Pick a content based on what the model sees in the supplied image.

    ``context`` is an optional open-shaped dict of additional signals
    (analogous to :func:`choose_by_context`); the image carries the main
    semantic load.
    """
    if not pool_contents:
        raise SelectionError("pool is empty — nothing to choose")

    candidates = await _candidates_for_prompt(pool_contents)
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    system = render("selection_system.j2")
    user_text = render("choose_by_image_user.j2", context=context, candidates=candidates)

    user_content: list[dict] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": mime_type, "data": image_b64},
        },
        {"type": "text", "text": user_text},
    ]

    image_meta = bus.ImageMeta(
        hash=hashlib.sha256(image_bytes).hexdigest()[:16],
        mime=mime_type,
        size_bytes=len(image_bytes),
    )
    raw: str | None = None
    try:
        raw = await _post_chat(system, user_content)
        result = _validate_choice(raw, {c.id for c in pool_contents if c.id is not None})
    except SelectionError as exc:
        _push_selection_event(
            variant="v3", system=system, user_prompt=user_text, raw=raw,
            result=None, error=str(exc), image_meta=image_meta,
        )
        raise
    _push_selection_event(
        variant="v3", system=system, user_prompt=user_text, raw=raw,
        result=result, error=None, image_meta=image_meta,
    )
    return result


def _push_selection_event(
    *,
    variant: str,
    system: str,
    user_prompt: str,
    raw: str | None,
    result: SelectionResult | None,
    error: str | None,
    image_meta: bus.ImageMeta | None = None,
) -> None:
    """Emit a selection event onto the debug bus. Never raises."""
    try:
        bus.push(
            bus.Event(
                kind="selection",
                request_id=bus.request_id_var.get(),
                variant=variant,  # type: ignore[arg-type]
                system_prompt=system,
                user_prompt=user_prompt,
                raw_response=raw,
                chosen_id=result.chosen_id if result else None,
                reasoning=result.reasoning if result else None,
                image_meta=image_meta,
                error=error,
            )
        )
    except Exception:
        # Debug bus must never affect the hot path. Swallow.
        pass
