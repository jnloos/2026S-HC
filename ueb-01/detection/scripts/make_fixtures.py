#!/usr/bin/env python3
"""Export a few labeled face fixtures from FairFace for the inference tests.

Picks, from the FairFace TEST/validation split, one clear example per target
where possible (a child, a young-adult male, a young-adult female, a senior),
runs YuNet to crop the aligned face, and writes them to
``arduino/python/tests/fixtures/`` as ``child.jpg``, ``young-adult_male.jpg``,
``young-adult_female.jpg``, ``senior.jpg``. Also writes an all-gray no-face
image ``noface.jpg`` and a ``fixtures_labels.json`` mapping filename -> expected
labels.

Only files inside the fixtures dir are written (the dir is created if missing).

Usage::

    python scripts/make_fixtures.py [--scan N]
"""

from __future__ import annotations

import argparse
import sys

import cv2
import numpy as np
from PIL import Image

from common import (
    FIXTURES_DIR,
    INPUT_SIZE,
    decode_class_label,
    load_fairface_dataset,
    map_age_to_band,
    map_gender_to_label,
    seed_everything,
    setup_logging,
    write_json,
)
from face_crop import FaceCropper

LOG = setup_logging("make_fixtures")

# Desired fixtures: filename -> (age_band, gender|None). gender None = any.
TARGETS = [
    ("child.jpg", "child", None),
    ("young-adult_male.jpg", "young-adult", "male"),
    ("young-adult_female.jpg", "young-adult", "female"),
    ("senior.jpg", "senior", None),
]


def _image_field(example: dict):
    for k in ("image", "img", "file"):
        if k in example:
            return example[k]
    return None


def _pick_split(ds):
    for name in ("test", "validation", "train"):
        if name in ds:
            return name
    return next(iter(ds.keys()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--scan",
        type=int,
        default=2000,
        help="Max rows to scan looking for matching fixtures.",
    )
    args = parser.parse_args()

    seed_everything()
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    try:
        cropper = FaceCropper()
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 1

    try:
        ds, cfg = load_fairface_dataset(subset=None, splits=None)
    except Exception as exc:  # noqa: BLE001
        LOG.error("Failed to load FairFace: %s", exc)
        return 1

    split = _pick_split(ds)
    data = ds[split]
    LOG.info("Using split %r (config=%s, n=%d)", split, cfg, len(data))
    age_feat = data.features.get("age")
    gender_feat = data.features.get("gender")

    remaining = {t[0]: t for t in TARGETS}
    expected: dict[str, dict] = {}
    scan_n = min(args.scan, len(data))

    for idx in range(scan_n):
        if not remaining:
            break
        ex = data[idx]
        band = map_age_to_band(decode_class_label(age_feat, ex.get("age")))
        glabel = map_gender_to_label(decode_class_label(gender_feat, ex.get("gender")))
        if band is None or glabel is None:
            continue
        # Find a still-needed target this row satisfies.
        match = None
        for fname, want_band, want_gender in remaining.values():
            if band == want_band and (want_gender is None or glabel == want_gender):
                match = (fname, want_band, want_gender)
                break
        if match is None:
            continue
        crop = cropper.crop_largest_face(_image_field(ex))
        if crop is None:
            continue
        fname = match[0]
        out_path = FIXTURES_DIR / fname
        cv2.imwrite(str(out_path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        expected[fname] = {"age_band": band, "gender": glabel, "has_face": True}
        LOG.info("Wrote fixture %s (band=%s gender=%s) from idx=%d", fname, band, glabel, idx)
        del remaining[fname]

    if remaining:
        LOG.warning(
            "Could not fill %d fixtures within %d rows: %s",
            len(remaining),
            scan_n,
            list(remaining.keys()),
        )

    # All-gray no-face fixture.
    gray = np.full((INPUT_SIZE, INPUT_SIZE, 3), 127, dtype=np.uint8)
    noface_path = FIXTURES_DIR / "noface.jpg"
    Image.fromarray(gray).save(noface_path)
    expected["noface.jpg"] = {"age_band": None, "gender": None, "has_face": False}
    LOG.info("Wrote no-face fixture %s", noface_path)

    write_json(FIXTURES_DIR / "fixtures_labels.json", expected)
    LOG.info("Wrote %d fixtures + labels to %s", len(expected), FIXTURES_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
