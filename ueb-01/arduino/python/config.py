"""Runtime configuration for the DigSig Arduino app.

Read once from environment variables at import time. Defaults are tuned for
local development on the board; production overrides go via env vars set
either in App Lab or on the board's user environment.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger("digsig.config")


def _load_runtime_env() -> None:
    """Overlay an optional ``runtime.env`` file onto ``os.environ``.

    Lets the deployed app be reconfigured fast — e.g. point ``CMS_URL`` at a
    laptop whose LAN IP keeps changing — by editing one file and re-syncing,
    with no App Lab env editing and no code change. Values in the file take
    precedence over the ambient environment, so the file is authoritative.
    Generated/managed by ``cli/configure.sh`` (and ``cli/dev.sh up``).

    Dependency-free: a tiny ``KEY=VALUE`` parser, since ``python-dotenv`` is not
    guaranteed to be installed on the board.
    """
    path = os.getenv("DIGSIG_ENV_FILE") or os.path.join(os.path.dirname(__file__), "runtime.env")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return
    loaded = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value
            loaded.append(key)
    if loaded:
        log.info("runtime.env loaded from %s: %s", path, ", ".join(loaded))


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"false", "0", "no", "off", ""}


@dataclass(frozen=True)
class Settings:
    cms_url: str
    pool_id: int
    audience_group: str
    audience_mode: Literal["static", "face"]
    audience_model_dir: str | None
    selector_mode: Literal["edge", "hybrid", "cloud"]
    trigger_mode: Literal["person", "timer"]
    timer_interval_sec: float
    person_debounce_sec: float
    llm_timeout_sec: float
    overlay_interval_sec: float
    enable_camera: bool
    debug: bool


def _load() -> Settings:
    _load_runtime_env()
    trigger_mode = os.getenv("TRIGGER_MODE", "person").strip().lower()
    if trigger_mode not in {"person", "timer"}:
        raise ValueError(
            f"TRIGGER_MODE must be 'person' or 'timer', got {trigger_mode!r}"
        )
    audience_mode = os.getenv("AUDIENCE_MODE", "static").strip().lower()
    if audience_mode not in {"static", "face"}:
        raise ValueError(
            f"AUDIENCE_MODE must be 'static' or 'face', got {audience_mode!r}"
        )
    # Which variant pipeline runs: edge (V1, on-device LLM) | hybrid (V2, cloud
    # selection from context) | cloud (V3, cloud vision+selection from image).
    selector_mode = os.getenv("SELECTOR_MODE", "edge").strip().lower()
    if selector_mode not in {"edge", "hybrid", "cloud"}:
        raise ValueError(
            f"SELECTOR_MODE must be 'edge', 'hybrid' or 'cloud', got {selector_mode!r}"
        )
    # ENABLE_CAMERA=false skips the video-detection brick entirely (no camera
    # capture, no EI-runner connection) — frees the CPU cores for the local
    # LLM during V1 timer-mode evaluation. Person-trigger needs it, so it
    # then falls back to the timer trigger.
    enable_camera = _bool(os.getenv("ENABLE_CAMERA"), default=True)
    if audience_mode == "face" and not enable_camera:
        raise ValueError(
            "AUDIENCE_MODE=face requires the camera, but ENABLE_CAMERA is false"
        )
    return Settings(
        cms_url=os.getenv("CMS_URL", "http://localhost:8000").rstrip("/"),
        pool_id=int(os.getenv("POOL_ID", "1")),
        audience_group=os.getenv("AUDIENCE_GROUP", "general"),
        audience_mode=audience_mode,  # type: ignore[arg-type]
        # None -> AudiencePipeline uses its bundled audience/models dir. Override
        # via AUDIENCE_MODEL_DIR for a custom board layout or tests.
        audience_model_dir=os.getenv("AUDIENCE_MODEL_DIR") or None,
        selector_mode=selector_mode,  # type: ignore[arg-type]
        trigger_mode=trigger_mode,  # type: ignore[arg-type]
        timer_interval_sec=float(os.getenv("TIMER_INTERVAL_SEC", "30")),
        person_debounce_sec=float(os.getenv("PERSON_DEBOUNCE_SEC", "5")),
        llm_timeout_sec=float(os.getenv("LLM_TIMEOUT_SEC", "240")),
        # Debug-preview demographic overlay cadence — independent of the pipeline
        # trigger, runs continuously in debug mode (see debug/audience_overlay.py).
        overlay_interval_sec=float(os.getenv("OVERLAY_INTERVAL_SEC", "1.0")),
        enable_camera=enable_camera,
        debug=_bool(os.getenv("DEBUG"), default=True),
    )


settings = _load()
