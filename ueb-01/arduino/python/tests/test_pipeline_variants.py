"""Off-board end-to-end harness for all three variant pipelines.

Builds the REAL pipeline (`Pipeline` + the real selectors + `WebUISink`) with
only the board-specific leaves mocked (a fake WebUI, a fake on-device LLM, a
fixture camera frame), and runs one full cycle per variant against the LOCAL
CMS API. The face-audience integration test additionally runs the real
in-process inference pipeline (no sidecar).

This proves V1/V2/V3 each complete `trigger -> audience -> select -> sink` and
publish a valid content choice, WITHOUT the board, the camera, or a real
on-device LLM. Requires the local API at CMS_URL (default :8000); the face test
additionally needs the ONNX models + cv2/onnxruntime. Tests skip cleanly when
those aren't available.

Run: `pytest arduino/python/tests/test_pipeline_variants.py`.
`cli/verify-pipelines.sh` boots the API and runs this automatically.
"""
from __future__ import annotations

import os
import pathlib

import pytest
import requests

# conftest.py puts arduino/python/ on sys.path. All of these are pure-Python
# (no board-only imports), so they import fine off-board.
from cms.client import CMSClient
from pipeline.pipeline import Pipeline
from sinks.web_ui import WebUISink
from pickers.edge import EdgeSelector
from pickers.hybrid import HybridSelector
from pickers.cloud import CloudSelector
from audience.static import StaticAudienceClassifier
from audience.face import FaceAudienceClassifier

API_URL = os.getenv("CMS_URL", "http://127.0.0.1:8000").rstrip("/")
POOL_ID = int(os.getenv("POOL_ID", "1"))
CHILD_CONTENT_ID = int(os.getenv("CHILD_CONTENT_ID", "4"))  # bakery "Kinder-Naschstation"

_FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def _up(url: str) -> bool:
    try:
        return requests.get(url, timeout=3).ok
    except requests.RequestException:
        return False


def _make_audience_pipeline():
    """Build the in-process AudiencePipeline, or None if models/deps are absent."""
    try:
        from audience.inference import AudiencePipeline
        return AudiencePipeline()
    except Exception:  # noqa: BLE001 — missing wheels or model files -> skip
        return None


_API_UP = _up(f"{API_URL}/openapi.json")
_AUDIENCE_PIPELINE = _make_audience_pipeline()

pytestmark = pytest.mark.skipif(not _API_UP, reason=f"local CMS API not reachable at {API_URL}")


class FakeUI:
    """Captures WebUI messages so we can assert what the sink published."""

    def __init__(self):
        self.messages: list[tuple[str, dict]] = []

    def send_message(self, msg_type: str, payload: dict) -> None:
        self.messages.append((msg_type, payload))


class FakeLLM:
    """Stand-in for the on-device LLM brick — returns a fixed id string."""

    def __init__(self, response: str):
        self._response = response

    def chat(self, prompt: str) -> str:
        return self._response


def _cms() -> CMSClient:
    return CMSClient(base_url=API_URL)


def _valid_ids() -> set[int]:
    pool = _cms().get_pool(POOL_ID)
    return {c["id"] for c in pool.get("contents", [])}


def _run(selector, classifier) -> dict:
    """Run one full pipeline cycle, return the published content dict."""
    ui = FakeUI()
    pipe = Pipeline(classifier=classifier, selector=selector, sink=WebUISink(ui))
    pipe.run_once({"type": "timer", "reason": "harness", "ts": "2026-06-05T00:00:00Z"})
    errors = [p for (t, p) in ui.messages if t == "pipeline_error"]
    assert not errors, f"pipeline reported an error: {errors}"
    updates = [p for (t, p) in ui.messages if t == "content_update"]
    assert updates, f"no content_update published; got messages={ui.messages}"
    return updates[-1]["content"]


def test_v1_edge_pipeline():
    """V1: real EdgeSelector + CMS pool fetch + mocked on-device LLM."""
    ids = _valid_ids()
    chosen = sorted(ids)[0]
    selector = EdgeSelector(cms=_cms(), pool_id=POOL_ID, local_llm=FakeLLM(str(chosen)))
    content = _run(selector, StaticAudienceClassifier(group="general"))
    assert content["variant"] == "v1"
    assert content["id"] in ids


def test_v2_hybrid_pipeline():
    """V2: real HybridSelector -> CMS choose-by-context (Claude)."""
    ids = _valid_ids()
    selector = HybridSelector(cms=_cms(), pool_id=POOL_ID)
    content = _run(selector, StaticAudienceClassifier(group="general"))
    assert content["variant"] == "v2"
    assert content["id"] in ids


def test_v3_cloud_pipeline():
    """V3: real CloudSelector -> CMS choose-by-img (Claude vision) with a fixture frame."""
    ids = _valid_ids()
    img = (_FIXTURES / "young-adult_female.jpg").read_bytes()
    selector = CloudSelector(
        cms=_cms(), pool_id=POOL_ID, frame_provider=lambda: (img, "image/jpeg")
    )
    content = _run(selector, StaticAudienceClassifier(group="general"))
    assert content["variant"] == "v3"
    assert content["id"] in ids


@pytest.mark.skipif(
    _AUDIENCE_PIPELINE is None,
    reason="in-process inference unavailable (ONNX models or cv2/onnxruntime missing)",
)
def test_face_audience_steers_v2_to_child_content():
    """Integration: child frame -> in-process inference -> families_with_children -> V2 picks the kids content."""
    img = (_FIXTURES / "child.jpg").read_bytes()
    classifier = FaceAudienceClassifier(
        pipeline=_AUDIENCE_PIPELINE, frame_provider=lambda: img
    )
    selector = HybridSelector(cms=_cms(), pool_id=POOL_ID)
    content = _run(selector, classifier)
    assert content["variant"] == "v2"
    assert content["id"] == CHILD_CONTENT_ID
