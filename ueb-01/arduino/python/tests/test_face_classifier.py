"""Unit tests for the camera-based audience classifier.

These run off-board (plain sync pytest) and mock the inference pipeline, so they
exercise :class:`audience.face.FaceAudienceClassifier` and
:class:`audience.frame_grabber.FrameGrabber` without needing the ONNX models, a
camera, or any ``arduino.*`` brick. Crucially they assert the classifier NEVER
raises and degrades to an ``unknown`` dict on failure.
"""
from __future__ import annotations

import base64

import pytest

from audience.face import FaceAudienceClassifier
from audience.frame_grabber import FrameGrabber


# --- fakes -------------------------------------------------------------------

CHILD_DICT = {
    "people_count": 1,
    "faces": [
        {"age_band": "child", "gender": "male", "age_conf": 0.82, "gender_conf": 0.66, "box": [10, 20, 30, 40]}
    ],
    "target_group": "families_with_children",
    "source": "face-local",
}

ADULT_DICT = {
    "people_count": 2,
    "faces": [
        {"age_band": "young-adult", "gender": "female", "age_conf": 0.71, "gender_conf": 0.93, "box": [0, 0, 50, 50]}
    ],
    "target_group": "young_women",
    "source": "face-local",
}


class FakePipeline:
    """Stands in for :class:`audience.inference.AudiencePipeline`."""

    def __init__(self, *, returns=None, raises=None):
        self._returns = returns
        self._raises = raises
        self.calls: list[bytes] = []

    def classify(self, jpeg_bytes: bytes) -> dict:
        self.calls.append(jpeg_bytes)
        if self._raises is not None:
            raise self._raises
        return self._returns


class FakeDetector:
    """Minimal stand-in exposing the brick's private frame attributes."""

    def __init__(self, *, last_camera_frame=None):
        self._last_camera_frame = last_camera_frame
        self._registered = []

    def on_detect_all(self, cb):
        self._registered.append(cb)


# --- FaceAudienceClassifier --------------------------------------------------

def test_child_dict_flows_through_unchanged():
    pipeline = FakePipeline(returns=CHILD_DICT)
    clf = FaceAudienceClassifier(pipeline=pipeline, frame_provider=lambda: b"jpegbytes")
    result = clf.classify()
    assert result == CHILD_DICT
    assert pipeline.calls == [b"jpegbytes"]


def test_adult_dict_flows_through_unchanged():
    pipeline = FakePipeline(returns=ADULT_DICT)
    clf = FaceAudienceClassifier(pipeline=pipeline, frame_provider=lambda: b"frame")
    assert clf.classify() == ADULT_DICT


def test_inference_error_returns_face_error_and_does_not_raise():
    pipeline = FakePipeline(raises=RuntimeError("boom"))
    clf = FaceAudienceClassifier(pipeline=pipeline, frame_provider=lambda: b"frame")
    result = clf.classify()  # must not raise
    assert result["source"] == "face-error"
    assert result["target_group"] == "unknown"
    assert result["people_count"] == 0
    assert result["faces"] == []


def test_unexpected_exception_returns_face_error_and_does_not_raise():
    pipeline = FakePipeline(raises=ValueError("undecodable"))
    clf = FaceAudienceClassifier(pipeline=pipeline, frame_provider=lambda: b"frame")
    result = clf.classify()  # must not raise
    assert result["source"] == "face-error"
    assert result["target_group"] == "unknown"


def test_no_frame_returns_face_no_frame():
    pipeline = FakePipeline(returns=CHILD_DICT)
    clf = FaceAudienceClassifier(pipeline=pipeline, frame_provider=lambda: None)
    result = clf.classify()
    assert result["source"] == "face-no-frame"
    assert result["target_group"] == "unknown"
    assert result["people_count"] == 0
    # The pipeline must not have been called when there's no frame.
    assert pipeline.calls == []


# --- FrameGrabber ------------------------------------------------------------

def test_frame_grabber_caches_callback_frame():
    detector = FakeDetector()
    grabber = FrameGrabber(detector)
    # The grabber should have registered exactly one callback.
    assert len(detector._registered) == 1
    cb = detector._registered[0]
    cb({"person": []}, frame=b"rawjpeg")
    assert grabber.get() == b"rawjpeg"


def test_frame_grabber_base64_fallback():
    raw = b"\xff\xd8\xff\xe0rawjpegdata"
    data_url = "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    detector = FakeDetector(last_camera_frame=data_url)
    grabber = FrameGrabber(detector)
    # No callback frame cached → falls back to decoding the preview data-URL.
    assert grabber.get() == raw


def test_frame_grabber_returns_none_without_any_frame():
    detector = FakeDetector(last_camera_frame=None)
    grabber = FrameGrabber(detector)
    assert grabber.get() is None


def test_frame_grabber_never_raises_on_bad_detector():
    # A detector lacking the expected attributes must not break get().
    class Bare:
        pass

    grabber = FrameGrabber(Bare())
    assert grabber.get() is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
