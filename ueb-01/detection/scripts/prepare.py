#!/usr/bin/env python3
"""Detect + crop aligned faces from FairFace and write a training-ready dataset.

For every FairFace image this runs YuNet (via ``FaceCropper``), takes the
largest detected face, expands the box ~20%, resizes to 112x112 and writes the
crop to ``detection/artifacts/crops/{split}/{idx}.jpg``. A parallel
``labels.csv`` (one per split dir, plus a combined one) records
``path, age_band, gender``. Rows whose face isn't detected are DROPPED.

Age and gender are mapped to the frozen spec (5 bands / {male,female}).

Usage::

    python scripts/prepare.py [--subset N] [--splits train test] [--score-threshold 0.6]
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter

from tqdm import tqdm

from common import (
    CROPS_DIR,
    decode_class_label,
    load_fairface_dataset,
    map_age_to_band,
    map_gender_to_label,
    seed_everything,
    setup_logging,
)
from face_crop import FaceCropper

LOG = setup_logging("prepare")

# FairFace HF splits are "train"/"validation". The frozen pipeline treats
# "validation" as the held-out test source for fixtures; we keep both.
DEFAULT_SPLITS = ["train", "validation"]


def _image_field(example: dict):
    for k in ("image", "img", "file"):
        if k in example:
            return example[k]
    return None


def prepare_split(ds_split, split_name: str, cropper: FaceCropper) -> list[dict]:
    """Process one split; return list of {path, age_band, gender} rows."""
    out_dir = CROPS_DIR / split_name
    out_dir.mkdir(parents=True, exist_ok=True)

    feats = ds_split.features
    age_feat = feats.get("age")
    gender_feat = feats.get("gender")

    rows: list[dict] = []
    age_counts: Counter = Counter()
    gender_counts: Counter = Counter()
    n_no_face = 0
    n_bad_label = 0

    for idx in tqdm(range(len(ds_split)), desc=f"prepare:{split_name}", unit="img"):
        ex = ds_split[idx]
        age_raw = decode_class_label(age_feat, ex.get("age"))
        gen_raw = decode_class_label(gender_feat, ex.get("gender"))
        band = map_age_to_band(age_raw)
        glabel = map_gender_to_label(gen_raw)
        if band is None or glabel is None:
            n_bad_label += 1
            continue

        crop = cropper.crop_largest_face(_image_field(ex))
        if crop is None:
            n_no_face += 1
            continue

        # Save crop (cv2 expects BGR for imwrite).
        import cv2

        out_path = out_dir / f"{idx}.jpg"
        cv2.imwrite(str(out_path), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        rel = out_path.relative_to(CROPS_DIR.parent)  # relative to artifacts/
        rows.append({"path": str(rel), "age_band": band, "gender": glabel})
        age_counts[band] += 1
        gender_counts[glabel] += 1

    LOG.info(
        "Split %r: kept=%d, no_face=%d, bad_label=%d",
        split_name,
        len(rows),
        n_no_face,
        n_bad_label,
    )
    LOG.info("  age bands: %s", dict(age_counts))
    LOG.info("  genders  : %s", dict(gender_counts))

    # Per-split labels.csv.
    _write_csv(out_dir / "labels.csv", rows)
    return rows


def _write_csv(path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["path", "age_band", "gender"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--subset", type=int, default=None, help="Cap rows per split.")
    parser.add_argument(
        "--splits", nargs="*", default=DEFAULT_SPLITS, help="Splits to process."
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.6,
        help="YuNet face-detection score threshold.",
    )
    parser.add_argument(
        "--expand",
        type=float,
        default=0.20,
        help="Fractional box expansion around the detected face.",
    )
    args = parser.parse_args()

    seed_everything()

    try:
        cropper = FaceCropper(score_threshold=args.score_threshold, expand=args.expand)
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 1

    try:
        ds, cfg = load_fairface_dataset(args.subset, args.splits)
    except Exception as exc:  # noqa: BLE001
        LOG.error("Failed to load FairFace: %s", exc)
        return 1
    LOG.info("FairFace loaded (config=%s). Splits available: %s", cfg, list(ds.keys()))

    CROPS_DIR.mkdir(parents=True, exist_ok=True)
    combined: list[dict] = []
    for split in args.splits:
        if split not in ds:
            LOG.warning("Split %r not in dataset; skipping.", split)
            continue
        combined.extend(prepare_split(ds[split], split, cropper))

    if not combined:
        LOG.error("No crops produced -- check YuNet model and dataset.")
        return 1

    _write_csv(CROPS_DIR / "labels.csv", combined)
    LOG.info("Wrote combined labels.csv with %d rows at %s", len(combined), CROPS_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
