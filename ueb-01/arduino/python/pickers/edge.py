"""Variant 1 — edge-only selection via the on-device LLM Brick.

"Edge-only" forbids cloud LLMs, not all LLMs. We fetch the pool from the CMS,
hand the candidates + context to the local `personal:llm` Brick, and parse a
JSON choice back. Same contract as V2 (the cloud variant), just locally.
"""
from __future__ import annotations

import json
import logging
import re
import time

from cms.client import CMSClient, CMSError
from debug.events import NULL_BUS, ms_since
from pickers.base import ContentSelector, SelectorError

log = logging.getLogger(__name__)


class _InferenceFailed(Exception):
    """Internal: the on-device LLM call itself failed (vs. a bad/missing id).

    Carries which phase failed (``retried``) and the text gathered so far so the
    caller can emit a consistent debug event before surfacing a SelectorError.
    """

    def __init__(self, cause: Exception, *, retried: bool, raw_so_far: str):
        super().__init__(str(cause))
        self.cause = cause
        self.retried = retried
        self.raw_so_far = raw_so_far

# The on-device model is small and slow (single-digit tok/s on the UNO Q CPU),
# so prompt size dominates latency. The content **description** is the primary
# selection signal (the fixtures spell out audience/weather/time cues there) —
# the raw HTML is not needed to pick and would bloat the prompt ~3-4x. We send
# name + description only. Set >0 to also include an HTML preview (slower).
_SNIPPET_PREVIEW_CHARS = 0

_SYSTEM_PROMPT = (
    "You are the content selector for a digital signage display.\n"
    "You receive a list of candidate snippets (each with a numeric id) and "
    "context signals about what is happening in front of the screen. "
    "Choose the single snippet whose description best matches the signals.\n\n"
    "Respond with ONLY that id as a bare integer — nothing else. "
    "No words, no JSON, no punctuation, no explanation. Just the number. "
    "The id MUST be one of the ids listed."
)


class EdgeSelector(ContentSelector):
    def __init__(self, *, cms: CMSClient, pool_id: int, local_llm, bus=None):
        self._cms = cms
        self._pool_id = pool_id
        self._llm = local_llm
        self._bus = bus or NULL_BUS
        # Cache the pool: V1 is the variant where the CMS makes no decisions,
        # so refetching every cycle is just bandwidth. Invalidates on error.
        self._pool_cache: dict | None = None

    def select(self, context: dict) -> dict:
        cache_hit = self._pool_cache is not None
        pool = self._fetch_pool()
        contents = pool.get("contents") or []
        if not contents:
            raise SelectorError(f"pool {self._pool_id} is empty")

        valid_ids = {c["id"] for c in contents}
        candidates = [{"id": c["id"], "name": c.get("name", "")} for c in contents]
        prompt = self._build_prompt(context, contents)

        t_inf = time.monotonic()
        try:
            chosen_id, raw_all, retried = self._choose_id(prompt, valid_ids)
        except _InferenceFailed as f:
            self._emit_selection(candidates, prompt, f.raw_so_far, None, "", f.retried, False,
                                 cache_hit, ms_since(t_inf), error=str(f.cause))
            phase = "retry" if f.retried else "call"
            raise SelectorError(f"local LLM {phase} failed: {f.cause}") from f.cause

        inference_ms = ms_since(t_inf)

        if chosen_id is None:
            # Hard fallback so the screen never goes blank.
            fallback = contents[0]
            log.warning(
                "local LLM gave no valid id after retry — falling back to id=%s",
                fallback["id"],
            )
            self._emit_selection(candidates, prompt, raw_all, fallback["id"],
                                 "invalid response, fell back", retried, True, cache_hit, inference_ms)
            return self._to_result(fallback, reasoning="")

        # V1 asks the model for the id only (no reasoning) — keeps the tiny
        # on-device model fast and avoids JSON-format failures.
        self._emit_selection(candidates, prompt, raw_all, chosen_id, "",
                             retried, False, cache_hit, inference_ms)
        chosen = next(c for c in contents if c["id"] == chosen_id)
        return self._to_result(chosen, reasoning="")

    def _emit_selection(self, candidates, prompt, raw, chosen_id, reasoning,
                        retried, fell_back, cache_hit, inference_ms, error=None):
        self._bus.emit(
            "selection",
            variant="v1",
            pool_id=self._pool_id,
            candidates=candidates,
            prompt=prompt,
            raw_response=raw,
            chosen_id=chosen_id,
            reasoning=reasoning,
            retried=retried,
            fell_back=fell_back,
            pool_cache_hit=cache_hit,
            inference_ms=inference_ms,
            error=error,
        )

    # --- helpers -------------------------------------------------------------

    def _choose_id(self, prompt: str, valid_ids: set[int]) -> tuple[int | None, str, bool]:
        """Ask the LLM for an id, retrying once with a stricter reminder.

        Returns ``(chosen_id, raw_all, retried)`` where ``chosen_id`` is None if
        the model still didn't give a valid id after the retry. Raises
        :class:`_InferenceFailed` if the LLM call itself errors.
        """
        try:
            raw = self._ask_llm(prompt)
        except Exception as e:  # noqa: BLE001 — brick API not fully known; be defensive
            raise _InferenceFailed(e, retried=False, raw_so_far="") from e

        raw_all = raw
        chosen_id = self._parse_id(raw, valid_ids)
        if chosen_id is not None:
            return chosen_id, raw_all, False

        # Retry once with a terser, stricter reminder.
        retry_prompt = prompt + (
            f"\n\nAnswer with ONLY one of these ids as a bare number: {sorted(valid_ids)}."
        )
        try:
            raw = self._ask_llm(retry_prompt)
        except Exception as e:  # noqa: BLE001
            raise _InferenceFailed(e, retried=True, raw_so_far=raw_all) from e
        raw_all = f"{raw_all}\n--- retry ---\n{raw}"
        return self._parse_id(raw, valid_ids), raw_all, True

    def _fetch_pool(self) -> dict:
        if self._pool_cache is not None:
            return self._pool_cache
        try:
            pool = self._cms.get_pool(self._pool_id)
        except CMSError as e:
            raise SelectorError(f"could not fetch pool: {e}") from e
        self._pool_cache = pool
        return pool

    def _build_prompt(self, context: dict, contents: list[dict]) -> str:
        # Order matters for speed: put the STABLE part (system prompt + candidate
        # list) FIRST and the small CHANGING part (context) LAST. The on-device
        # llama.cpp runner caches the KV of the common prompt prefix across
        # calls, so after the first selection only the short context tail is
        # re-evaluated — prompt-eval (the bottleneck) drops from ~80s to seconds.
        lines: list[str] = [_SYSTEM_PROMPT, "", "Candidate contents:"]
        for c in contents:
            lines.append(f"[id={c['id']}] name={json.dumps(c.get('name', ''))}")
            desc = c.get("description") or ""
            if desc:
                lines.append(f"description: {desc}")
            # HTML preview only if explicitly enabled — see _SNIPPET_PREVIEW_CHARS.
            if _SNIPPET_PREVIEW_CHARS > 0:
                html = (c.get("html") or "").strip()
                if len(html) > _SNIPPET_PREVIEW_CHARS:
                    html = html[:_SNIPPET_PREVIEW_CHARS] + "…"
                if html:
                    lines.append(f"html: {html}")
            lines.append("---")
        lines.append("")
        lines.append("Context signals:")
        if context:
            for k, v in context.items():
                lines.append(f"- {k}: {json.dumps(v, default=str)}")
        else:
            lines.append("(no context provided)")
        lines.append("")
        lines.append("Reply with only the id of the best-matching candidate.")
        return "\n".join(lines)

    def _ask_llm(self, prompt: str) -> str:
        """Call the on-device LLM Brick. Returns the raw text response.

        The `personal:llm` Brick's exact API isn't pinned in the knowledge base
        — App Lab examples use `chat()`/`chat_stream()`. We try a few common
        shapes so this code keeps working across small brick API changes.
        """
        for method_name in ("chat", "generate", "complete"):
            method = getattr(self._llm, method_name, None)
            if callable(method):
                result = method(prompt)
                # If the brick returns a streaming iterator, collapse it.
                if isinstance(result, str):
                    return result
                try:
                    return "".join(chunk for chunk in result)
                except TypeError:
                    return str(result)
        # Fallback: assume the brick is itself callable.
        if callable(self._llm):
            return str(self._llm(prompt))
        raise RuntimeError(
            "local LLM brick exposes none of: chat/generate/complete/callable"
        )

    @staticmethod
    def _parse_id(raw: str, valid_ids: set[int]) -> int | None:
        """Return the first integer in the response that is a valid pool id.

        The model is asked for a bare id; this stays robust if it adds stray
        text anyway (e.g. "id 3" or "The answer is 3.").
        """
        if not raw:
            return None
        for token in re.findall(r"-?\d+", raw):
            try:
                n = int(token)
            except ValueError:
                continue
            if n in valid_ids:
                return n
        return None

    @staticmethod
    def _to_result(content: dict, *, reasoning: str) -> dict:
        return {
            "id": content["id"],
            "name": content.get("name", ""),
            "description": content.get("description", ""),
            "html": content.get("html", ""),
            "reasoning": reasoning,
            "variant": "v1",
        }
