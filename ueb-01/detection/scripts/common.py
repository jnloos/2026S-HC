"""Shared constants and helpers for the audience-classifier training pipeline.

This module is imported by the other scripts in ``detection/scripts``. It owns
the FROZEN label spec (age bands, gender order, FairFace -> band mapping) and the
preprocessing constants, so that every stage of the pipeline (prepare, train,
export, sanity) agrees on the exact same contract the inference pipeline consumes.
"""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path

# --------------------------------------------------------------------------- #
# Repo-relative paths (this file lives at detection/scripts/common.py).
# --------------------------------------------------------------------------- #
SCRIPTS_DIR = Path(__file__).resolve().parent
AUDIENCE_DIR = SCRIPTS_DIR.parent                      # detection
MODELS_DIR = AUDIENCE_DIR / "models"
ARTIFACTS_DIR = AUDIENCE_DIR / "artifacts"
DATA_DIR = AUDIENCE_DIR / ".data"
CROPS_DIR = ARTIFACTS_DIR / "crops"
REPO_ROOT = AUDIENCE_DIR.parent
# Inference now runs in-process inside the App, so the test fixtures live with
# the App's tests (arduino/python/tests/fixtures), not in a sidecar.
FIXTURES_DIR = REPO_ROOT / "arduino" / "python" / "tests" / "fixtures"

YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
YUNET_PATH = MODELS_DIR / YUNET_FILENAME
# opencv_zoo stores model weights via Git LFS, so the plain raw.githubusercontent
# URL returns a ~130-byte LFS pointer, not the model. The media.githubusercontent
# "/media/" endpoint serves the actual LFS object.
YUNET_URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
)

ONNX_MODEL_PATH = MODELS_DIR / "audience_classifier.onnx"
ONNX_INT8_PATH = MODELS_DIR / "audience_classifier.int8.onnx"
LABELS_PATH = MODELS_DIR / "labels.json"
MODEL_CARD_PATH = MODELS_DIR / "model_card.md"
BEST_CKPT_PATH = ARTIFACTS_DIR / "best.pt"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"

# --------------------------------------------------------------------------- #
# FROZEN SPEC --- order matters, the inference pipeline indexes logits by these lists.
# --------------------------------------------------------------------------- #
AGE_BANDS = ["child", "teen", "young-adult", "adult", "senior"]
GENDERS = ["male", "female"]
INPUT_SIZE = 112
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
COLOR_ORDER = "RGB"

ONNX_INPUT_NAME = "input"
ONNX_AGE_OUTPUT = "age_logits"
ONNX_GENDER_OUTPUT = "gender_logits"

SEED = 42

# FairFace ``age`` is a string bin label. Map each bin to one coarse band.
FAIRFACE_AGE_TO_BAND = {
    "0-2": "child",
    "3-9": "child",
    "10-19": "teen",
    "20-29": "young-adult",
    "30-39": "adult",
    "40-49": "adult",
    "50-59": "adult",
    "60-69": "senior",
    "more than 70": "senior",
}

# FairFace ``gender`` is "Male"/"Female".
FAIRFACE_GENDER_TO_LABEL = {
    "Male": "male",
    "Female": "female",
}

AGE_BAND_TO_IDX = {band: i for i, band in enumerate(AGE_BANDS)}
GENDER_TO_IDX = {g: i for i, g in enumerate(GENDERS)}


def labels_json() -> dict:
    """Return the exact ``labels.json`` structure the inference pipeline reads."""
    return {
        "input_size": INPUT_SIZE,
        "mean": MEAN,
        "std": STD,
        "color_order": COLOR_ORDER,
        "age_bands": AGE_BANDS,
        "genders": GENDERS,
        "onnx_input": ONNX_INPUT_NAME,
        "onnx_outputs": {"age": ONNX_AGE_OUTPUT, "gender": ONNX_GENDER_OUTPUT},
        "child_band": "child",
        "thresholds": {"face_score": 0.6},
        "target_group_rules": {
            "child_any": "families_with_children",
            "dominant": {
                "teen|male": "teens",
                "teen|female": "teens",
                "young-adult|female": "young_women",
                "young-adult|male": "young_men",
                "adult|female": "adult_women",
                "adult|male": "adult_men",
                "senior|male": "seniors",
                "senior|female": "seniors",
            },
            "default": "adults_mixed",
        },
    }


def map_age_to_band(age_value) -> str | None:
    """Map a FairFace ``age`` field (string bin, or class index) to a band.

    Datasets sometimes expose the column as a ClassLabel int; callers should
    pass the *string* form. Returns ``None`` for anything unrecognized.
    """
    if age_value is None:
        return None
    return FAIRFACE_AGE_TO_BAND.get(str(age_value).strip())


def map_gender_to_label(gender_value) -> str | None:
    """Map a FairFace ``gender`` field ("Male"/"Female") to {male,female}."""
    if gender_value is None:
        return None
    return FAIRFACE_GENDER_TO_LABEL.get(str(gender_value).strip())


def seed_everything(seed: int = SEED) -> None:
    """Seed python/numpy/torch RNGs for reproducibility."""
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:  # numpy should be present, but never fail seeding on it
        pass
    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        try:
            torch.use_deterministic_algorithms(False)
        except Exception:
            pass
    except Exception:
        pass


def setup_logging(name: str) -> logging.Logger:
    """Return a configured module logger with a simple console format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(name)


def write_json(path: Path, obj: dict) -> None:
    """Pretty-write ``obj`` as JSON, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# --------------------------------------------------------------------------- #
# Shared FairFace loading (used by prepare.py and make_fixtures.py).
# --------------------------------------------------------------------------- #
_FAIRFACE_ID = "HuggingFaceM4/FairFace"
_FAIRFACE_CONFIGS = ["1.25", "0.25", None]


def load_fairface_dataset(subset: int | None = None, splits=None):
    """Load FairFace via HF ``datasets``, trying config candidates in order.

    Returns ``(dataset_dict, config_used)``. Optionally caps each requested
    split to ``subset`` rows. ``splits`` limits which splits are capped (the
    full DatasetDict is still returned).
    """
    from datasets import load_dataset

    last_err = None
    for cfg in _FAIRFACE_CONFIGS:
        try:
            if cfg is None:
                ds = load_dataset(_FAIRFACE_ID, cache_dir=str(DATA_DIR))
            else:
                ds = load_dataset(_FAIRFACE_ID, cfg, cache_dir=str(DATA_DIR))
            if subset is not None:
                for split in list(ds.keys()):
                    if splits and split not in splits:
                        continue
                    n = min(subset, len(ds[split]))
                    ds[split] = ds[split].select(range(n))
            return ds, (cfg or "default")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise RuntimeError(f"Could not load FairFace with any config: {last_err}")


def decode_class_label(feature, value):
    """Convert a ClassLabel int to its string name when needed, else passthrough."""
    try:
        if hasattr(feature, "int2str") and isinstance(value, int):
            return feature.int2str(value)
    except Exception:  # noqa: BLE001
        pass
    return value
