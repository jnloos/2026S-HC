"""Crop dataset + preprocessing transforms for the audience classifier.

Reads the ``labels.csv`` produced by ``prepare.py`` and yields
``(tensor, age_idx, gender_idx)`` triples. Preprocessing matches the frozen
spec exactly: RGB, resize to ``input_size``, /255, ImageNet normalize. The same
normalization is baked into the ONNX-consumer contract, so the inference pipeline must
reproduce it.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

from common import (
    AGE_BAND_TO_IDX,
    ARTIFACTS_DIR,
    GENDER_TO_IDX,
    INPUT_SIZE,
    MEAN,
    STD,
)

_MEAN = np.array(MEAN, dtype=np.float32).reshape(1, 1, 3)
_STD = np.array(STD, dtype=np.float32).reshape(1, 1, 3)


def preprocess_pil(img: Image.Image, input_size: int = INPUT_SIZE) -> np.ndarray:
    """RGB resize -> /255 -> ImageNet normalize, returning CHW float32."""
    img = img.convert("RGB").resize((input_size, input_size), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - _MEAN) / _STD
    return np.transpose(arr, (2, 0, 1)).copy()  # HWC -> CHW


def load_rows(csv_path: Path) -> list[dict]:
    """Read a labels.csv into a list of dict rows."""
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class CropDataset(Dataset):
    """Dataset over prepared face crops referenced by ``labels.csv``.

    ``rows`` is a list of dicts with keys ``path`` (relative to
    ``detection/artifacts``), ``age_band`` and ``gender``.
    """

    def __init__(
        self,
        rows: list[dict],
        input_size: int = INPUT_SIZE,
        augment: bool = False,
        root: Path = ARTIFACTS_DIR,
    ) -> None:
        self.rows = rows
        self.input_size = input_size
        self.augment = augment
        self.root = root

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def age_targets(self) -> list[int]:
        """Age-band class index per row (used by the balanced sampler)."""
        return [AGE_BAND_TO_IDX[r["age_band"]] for r in self.rows]

    def _resolve(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    def __getitem__(self, idx: int):
        row = self.rows[idx]
        img = Image.open(self._resolve(row["path"]))
        if self.augment:
            # Light, label-preserving augmentation: horizontal flip.
            import random

            if random.random() < 0.5:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
        x = preprocess_pil(img, self.input_size)
        age_idx = AGE_BAND_TO_IDX[row["age_band"]]
        gender_idx = GENDER_TO_IDX[row["gender"]]
        return (
            torch.from_numpy(x),
            torch.tensor(age_idx, dtype=torch.long),
            torch.tensor(gender_idx, dtype=torch.long),
        )
