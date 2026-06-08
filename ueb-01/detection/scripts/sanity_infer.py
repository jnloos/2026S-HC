#!/usr/bin/env python3
"""Smoke-test the exported ONNX with onnxruntime on a few crops + fixtures.

Loads ``models/audience_classifier.onnx`` via onnxruntime, runs it on a handful
of held-out training crops (from ``artifacts/crops``) and, if present, on the
fixtures in ``arduino/python/tests/fixtures/*.jpg``. Prints the predicted
age band / gender + confidences. Exits nonzero if the model can't load.

Usage::

    python scripts/sanity_infer.py [--n 8]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from common import (
    AGE_BANDS,
    CROPS_DIR,
    FIXTURES_DIR,
    GENDERS,
    INPUT_SIZE,
    ONNX_AGE_OUTPUT,
    ONNX_GENDER_OUTPUT,
    ONNX_INPUT_NAME,
    ONNX_MODEL_PATH,
    seed_everything,
    setup_logging,
)
from dataset import preprocess_pil

LOG = setup_logging("sanity_infer")


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - x.max(axis=-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=-1, keepdims=True)


def load_session():
    """Create an onnxruntime session for the exported model."""
    import onnxruntime as ort

    if not ONNX_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"ONNX model not found at {ONNX_MODEL_PATH}. Run export_onnx.py first."
        )
    sess = ort.InferenceSession(
        str(ONNX_MODEL_PATH), providers=["CPUExecutionProvider"]
    )
    return sess


def predict(sess, img: Image.Image, input_size: int) -> dict:
    """Run one image, return predicted band/gender + confidences."""
    x = preprocess_pil(img, input_size)[None, ...].astype(np.float32)
    outs = sess.run([ONNX_AGE_OUTPUT, ONNX_GENDER_OUTPUT], {ONNX_INPUT_NAME: x})
    age_p = _softmax(outs[0])[0]
    gen_p = _softmax(outs[1])[0]
    ai, gi = int(age_p.argmax()), int(gen_p.argmax())
    return {
        "age_band": AGE_BANDS[ai],
        "age_conf": float(age_p[ai]),
        "gender": GENDERS[gi],
        "gender_conf": float(gen_p[gi]),
    }


def _gather_crops(n: int) -> list[Path]:
    paths: list[Path] = []
    for split_dir in sorted(CROPS_DIR.glob("*")):
        if split_dir.is_dir():
            paths.extend(sorted(split_dir.glob("*.jpg")))
    return paths[:n]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=8, help="Held-out crops to test.")
    parser.add_argument("--input-size", type=int, default=INPUT_SIZE)
    args = parser.parse_args()

    seed_everything()
    try:
        sess = load_session()
    except Exception as exc:  # noqa: BLE001
        LOG.error("Could not load ONNX session: %s", exc)
        return 2
    LOG.info("Loaded ONNX session for %s", ONNX_MODEL_PATH.name)

    tested = 0
    crops = _gather_crops(args.n)
    if crops:
        LOG.info("--- crops (%d) ---", len(crops))
        for p in crops:
            try:
                res = predict(sess, Image.open(p), args.input_size)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("  %s: failed (%s)", p.name, exc)
                continue
            LOG.info(
                "  %-24s -> %-12s (%.2f) | %-6s (%.2f)",
                p.name,
                res["age_band"],
                res["age_conf"],
                res["gender"],
                res["gender_conf"],
            )
            tested += 1
    else:
        LOG.info("No crops found under %s (run prepare.py to populate).", CROPS_DIR)

    fixtures = sorted(FIXTURES_DIR.glob("*.jpg")) if FIXTURES_DIR.exists() else []
    if fixtures:
        LOG.info("--- fixtures (%d) ---", len(fixtures))
        for p in fixtures:
            try:
                res = predict(sess, Image.open(p), args.input_size)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("  %s: failed (%s)", p.name, exc)
                continue
            LOG.info(
                "  %-24s -> %-12s (%.2f) | %-6s (%.2f)",
                p.name,
                res["age_band"],
                res["age_conf"],
                res["gender"],
                res["gender_conf"],
            )
            tested += 1
    else:
        LOG.info("No fixtures at %s (run make_fixtures.py to create them).", FIXTURES_DIR)

    if tested == 0:
        LOG.warning("Session loaded but no images were available to test.")
    LOG.info("Sanity inference complete (%d images).", tested)
    return 0


if __name__ == "__main__":
    sys.exit(main())
