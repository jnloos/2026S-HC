"""DigSig — composition root.

Wires the strategy slots together according to env-driven config and starts
the App. New variants/features should be added by writing new strategy
implementations and swapping them in here — no other module knows about
specific variants.
"""
from __future__ import annotations

import logging
import threading
import time

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI

# Local packages live alongside this file (python/ is on sys.path when the App
# runs). The bricks are optional at import time — we degrade gracefully if a
# brick isn't available in this App's manifest.
from config import settings
from audience.static import StaticAudienceClassifier
from audience.face import FaceAudienceClassifier
from audience.frame_grabber import FrameGrabber
from cms.client import CMSClient
from debug.events import BusLogHandler, DebugBus, HealthReporter
from debug.streamer import DebugStreamer
from debug.audience_overlay import AudienceOverlayWorker
from pickers.edge import EdgeSelector
from pickers.hybrid import HybridSelector
from pickers.cloud import CloudSelector
from pipeline.pipeline import Pipeline
from sinks.web_ui import WebUISink
from triggers.person import PersonTrigger
from triggers.timer import TimerTrigger

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("digsig")


def _make_detector():
    """Construct the VideoObjectDetection brick on demand.

    Person-trigger needs it; debug mode benefits from it but works without.
    Constructing it eagerly when neither path needs it would burn resources.
    """
    if not settings.enable_camera:
        # Explicitly disabled — keeps the CPU free for the local LLM. Person
        # trigger then falls back to timer (handled in main()).
        log.info("camera disabled (ENABLE_CAMERA=false) — no detector / preview")
        return None
    if settings.trigger_mode != "person" and not settings.debug and settings.audience_mode != "face":
        return None
    try:
        from arduino.app_bricks.video_objectdetection import VideoObjectDetection
    except ImportError:
        log.warning("video_object_detection brick not available — person trigger / debug disabled")
        return None
    # camera_preview makes the brick stream the live camera frame, which the
    # debug PiP renders. Only enable it in debug mode — it costs extra bandwidth.
    return VideoObjectDetection(
        confidence=0.5,
        camera_preview=settings.debug or settings.audience_mode == "face",
    )


def _make_local_llm():
    try:
        from personal_llm import LargeLanguageModel
    except ImportError:
        log.error("personal:llm brick not available — V1 selector cannot run")
        raise
    # The on-device model on the UNO Q CPU is slow (single-digit tok/s); a real
    # selection can take ~1-2 min. Give it a generous timeout so a call still
    # completes, but never hangs the pipeline thread indefinitely on a stall.
    # temperature=0: deterministic — a small model follows the strict format
    # far more reliably. max_tokens=16: V1 only needs the model to emit a single
    # integer id (no reasoning), so cap generation hard — generation is the
    # bottleneck (~1.4 tok/s), so fewer output tokens is the biggest speedup.
    return LargeLanguageModel(
        timeout=settings.llm_timeout_sec, temperature=0.0, max_tokens=16
    )


def _make_audience_pipeline():
    """Construct the in-process audience-inference pipeline, or None.

    The heavy deps (onnxruntime, cv2) and the ONNX model files may be absent on
    a given board. Rather than crash, we degrade: a None return makes the caller
    fall back to the static audience classifier (same spirit as the optional
    bricks above).
    """
    try:
        from audience.inference import AudiencePipeline
        return AudiencePipeline(model_dir=settings.audience_model_dir)
    except Exception:  # noqa: BLE001 — missing wheels or model files must not crash the app
        log.exception("audience inference unavailable — falling back to static audience")
        return None


def main() -> None:
    log.info(
        "starting DigSig: trigger=%s cms=%s pool=%s audience=%s debug=%s",
        settings.trigger_mode,
        settings.cms_url,
        settings.pool_id,
        settings.audience_group,
        settings.debug,
    )

    ui = WebUI()
    detector = _make_detector()

    # Debug event channel — no-op unless debug. Forward WARNING+ logs to the UI.
    bus = DebugBus(ui, enabled=settings.debug)
    if settings.debug:
        logging.getLogger().addHandler(BusLogHandler(bus))

    cms = CMSClient(base_url=settings.cms_url, bus=bus)
    # One shared camera-frame source for everything that needs it (cloud selector,
    # face audience, debug overlay) — avoids registering several detection
    # callbacks on the brick. None when there's no camera.
    grabber = FrameGrabber(detector) if detector is not None else None
    # Pick the variant pipeline. Only V1 (edge) needs the on-device LLM brick;
    # V2/V3 delegate selection to the CMS, so we don't construct (and don't
    # require) the local LLM for them.
    local_llm = None
    if settings.selector_mode == "edge":
        local_llm = _make_local_llm()
        selector = EdgeSelector(cms=cms, pool_id=settings.pool_id, local_llm=local_llm, bus=bus)
        log.info("selector: edge (V1, on-device LLM)")
    elif settings.selector_mode == "hybrid":
        selector = HybridSelector(cms=cms, pool_id=settings.pool_id, bus=bus)
        log.info("selector: hybrid (V2, cloud selection from context)")
    else:  # cloud (V3)
        if detector is None:
            log.error(
                "SELECTOR_MODE=cloud needs the camera, but no detector — falling back to edge (V1)"
            )
            local_llm = _make_local_llm()
            selector = EdgeSelector(cms=cms, pool_id=settings.pool_id, local_llm=local_llm, bus=bus)
        else:
            def _frame_jpeg():
                b = grabber.get()
                return (b, "image/jpeg") if b else (None, None)

            selector = CloudSelector(
                cms=cms, pool_id=settings.pool_id, frame_provider=_frame_jpeg, bus=bus
            )
            log.info("selector: cloud (V3, cloud vision+selection from image)")
    # Audience classification. Face mode needs both a camera frame source and a
    # working in-process inference pipeline; if either is missing we degrade to
    # the static classifier. The pipeline is shared with the debug overlay.
    audience_pipeline = None
    if settings.audience_mode == "face" and grabber is not None:
        audience_pipeline = _make_audience_pipeline()
    if audience_pipeline is not None:
        classifier = FaceAudienceClassifier(
            pipeline=audience_pipeline, frame_provider=grabber.get, bus=bus
        )
        log.info("audience: in-process face classifier (models=%s)", audience_pipeline.model_dir)
    else:
        if settings.audience_mode == "face":
            log.warning("AUDIENCE_MODE=face requested but no camera/inference — falling back to static audience")
        classifier = StaticAudienceClassifier(group=settings.audience_group)
        log.info("audience: static classifier (group=%s)", settings.audience_group)
    sink = WebUISink(ui)
    pipeline = Pipeline(classifier=classifier, selector=selector, sink=sink, bus=bus)

    if settings.trigger_mode == "timer":
        trigger = TimerTrigger(interval_sec=settings.timer_interval_sec)
    else:
        if detector is None:
            log.warning("person trigger requested but no detector — falling back to timer")
            trigger = TimerTrigger(interval_sec=settings.timer_interval_sec)
        else:
            trigger = PersonTrigger(detector, debounce_sec=settings.person_debounce_sec)

    trigger.start(on_fire=pipeline.run_once)

    # Re-broadcast the current content periodically so a browser tab that
    # connects after a selection still shows it (content_update is otherwise a
    # one-shot broadcast). The frontend ignores duplicates, so this is
    # flicker-free. Always on — signage must show content to any viewer.
    def _content_rebroadcast() -> None:
        while True:
            time.sleep(8)
            try:
                sink.resend_last()
            except Exception:  # noqa: BLE001 — never let re-broadcast kill the app
                log.debug("content re-broadcast failed", exc_info=True)

    threading.Thread(target=_content_rebroadcast, name="content-rebroadcast", daemon=True).start()

    if settings.debug and detector is not None:
        DebugStreamer(ui=ui, detector=detector).start()

    # Independent demographic overlay for the debug preview — classifies the live
    # camera frame at its own (higher) cadence in-process and emits the
    # "audience" debug event, decoupled from the pipeline trigger/selector. Reuses
    # the pipeline built for the audience classifier above (constructed on demand
    # if debug is on but the selector path didn't need one).
    if settings.debug and grabber is not None:
        overlay_pipeline = audience_pipeline or _make_audience_pipeline()
        if overlay_pipeline is not None:
            AudienceOverlayWorker(
                bus=bus,
                frame_provider=grabber.get,
                pipeline=overlay_pipeline,
                interval_sec=settings.overlay_interval_sec,
            ).start()

    # Initial handshake — tells the browser whether to render the debug PiP.
    # Also re-broadcast periodically by HealthReporter so a browser that connects
    # after startup (the normal case) still receives it.
    handshake = {
        "debug": settings.debug,
        "trigger_mode": settings.trigger_mode,
        "pool_id": settings.pool_id,
    }
    ui.send_message("config", handshake)

    # Health/readiness reporting for the debug window (CMS dot, brick status,
    # config snapshot). The reporter re-broadcasts every few seconds so a
    # late-connecting browser tab still gets the snapshot.
    if settings.debug:
        _variant_label = {"edge": "v1 (edge)", "hybrid": "v2 (hybrid)", "cloud": "v3 (cloud)"}
        config_snapshot = {
            "variant": _variant_label.get(settings.selector_mode, settings.selector_mode),
            "selector_mode": settings.selector_mode,
            "trigger_mode": settings.trigger_mode,
            "pool_id": settings.pool_id,
            "audience_group": settings.audience_group,
            "audience_mode": settings.audience_mode,
            "audience_inproc": audience_pipeline is not None,
            "cms_url": settings.cms_url,
        }
        HealthReporter(
            bus=bus,
            cms=cms,
            config=config_snapshot,
            llm_ok=local_llm is not None,
            detector_ok=detector is not None,
            camera_ok=detector is not None,
            ui=ui,
            handshake=handshake,
        ).start()


main()

# App.run() must be the very last statement — keeps the App alive so Bridge
# providers stay callable and bricks keep running.
App.run()
