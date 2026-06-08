"""Real-model tests for the in-process audience inference pipeline.

Exercises :class:`audience.inference.AudiencePipeline` against the labeled
fixtures in ``tests/fixtures/``. Skipped cleanly when the ONNX models or the
heavy wheels (``cv2`` / ``onnxruntime``) aren't present, so a plain off-board
``pytest`` run doesn't hard-fail on a machine without them.

The fixture images are produced by the training pipeline
(``detection/scripts/make_fixtures.py``); they are NOT created here.
"""

from __future__ import annotations

import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(HERE, "fixtures")
# Default to the bundled app models; AUDIENCE_MODEL_DIR overrides (e.g. CI).
BUNDLED_MODELS_DIR = os.path.abspath(
    os.path.join(HERE, "..", "audience", "models")
)

REQUIRED_MODELS = (
    "labels.json",
    "audience_classifier.onnx",
    "face_detection_yunet_2023mar.onnx",
)


def _resolve_model_dir() -> str | None:
    """Return a model dir containing all required files, else None."""
    candidates = []
    env_dir = os.environ.get("AUDIENCE_MODEL_DIR")
    if env_dir:
        candidates.append(env_dir)
    candidates.append(BUNDLED_MODELS_DIR)
    for cand in candidates:
        if all(os.path.isfile(os.path.join(cand, f)) for f in REQUIRED_MODELS):
            return cand
    return None


def _have_deps() -> bool:
    try:
        import cv2  # noqa: F401
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def _read_fixture(name: str) -> bytes:
    with open(os.path.join(FIXTURES_DIR, name), "rb") as fh:
        return fh.read()


def _fixtures_present(*names: str) -> bool:
    return all(os.path.isfile(os.path.join(FIXTURES_DIR, n)) for n in names)


MODEL_DIR = _resolve_model_dir()
_SKIP_REASON = (
    "real ONNX models / cv2+onnxruntime not available; skipping in-process "
    "inference tests"
)
_RUNNABLE = MODEL_DIR is not None and _have_deps()


@pytest.mark.skipif(not _RUNNABLE, reason=_SKIP_REASON)
class TestAudiencePipeline:
    @pytest.fixture(scope="class")
    def pipeline(self):
        from audience.inference import AudiencePipeline

        return AudiencePipeline(model_dir=MODEL_DIR)

    def test_child_fixture(self, pipeline):
        if not _fixtures_present("child.jpg"):
            pytest.skip("child.jpg fixture not present")
        result = pipeline.classify(_read_fixture("child.jpg"))
        assert result["people_count"] >= 1
        assert any(f["age_band"] == "child" for f in result["faces"])
        assert result["target_group"] == "families_with_children"
        assert result["source"] == "face-local"

    def test_young_adult_female_fixture(self, pipeline):
        if not _fixtures_present("young-adult_female.jpg"):
            pytest.skip("young-adult_female.jpg fixture not present")
        result = pipeline.classify(_read_fixture("young-adult_female.jpg"))
        assert result["people_count"] >= 1
        assert any(
            f["age_band"] == "young-adult" and f["gender"] == "female"
            for f in result["faces"]
        )

    def test_noface_fixture(self, pipeline):
        if not _fixtures_present("noface.jpg"):
            pytest.skip("noface.jpg fixture not present")
        result = pipeline.classify(_read_fixture("noface.jpg"))
        assert result["people_count"] == 0
        assert result["faces"] == []
        assert result["target_group"] == "unknown"
        assert result["source"] == "face-local"

    def test_undecodable_buffer_raises_value_error(self, pipeline):
        with pytest.raises(ValueError):
            pipeline.classify(b"not-a-jpeg")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
