"""YuNet face detection + aligned-crop helper shared by prepare/make_fixtures.

Wraps ``cv2.FaceDetectorYN`` (loaded from the fetched YuNet ONNX) and exposes a
single ``crop_largest_face`` that returns a 112x112 RGB crop (or ``None`` when
no face is detected). The crop box is the detected face expanded by ~20% so the
classifier sees a bit of context (forehead/chin), matching how the inference pipeline will
crop at inference time.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from common import INPUT_SIZE, YUNET_PATH


class FaceCropper:
    """Detect the largest face in an image and return an aligned square crop."""

    def __init__(
        self,
        model_path: Path = YUNET_PATH,
        score_threshold: float = 0.6,
        nms_threshold: float = 0.3,
        top_k: int = 50,
        expand: float = 0.20,
        out_size: int = INPUT_SIZE,
    ) -> None:
        if not model_path.exists():
            raise FileNotFoundError(
                f"YuNet model not found at {model_path}. Run fetch_models.py first."
            )
        self.expand = expand
        self.out_size = out_size
        # Input size is reset per-image via setInputSize().
        self.detector = cv2.FaceDetectorYN.create(
            str(model_path),
            "",
            (320, 320),
            score_threshold,
            nms_threshold,
            top_k,
        )

    def _detect(self, bgr: np.ndarray) -> np.ndarray | None:
        """Run YuNet, return the highest-area face row or None."""
        h, w = bgr.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(bgr)
        if faces is None or len(faces) == 0:
            return None
        # faces columns: x, y, w, h, [landmarks...], score
        areas = faces[:, 2] * faces[:, 3]
        return faces[int(np.argmax(areas))]

    def crop_largest_face(self, image) -> np.ndarray | None:
        """Return an ``out_size`` x ``out_size`` RGB crop of the largest face.

        ``image`` may be a PIL.Image or an HxWx3 numpy array (RGB). Returns
        ``None`` if no face is detected.
        """
        rgb = _to_rgb_array(image)
        if rgb is None:
            return None
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        face = self._detect(bgr)
        if face is None:
            return None

        h, w = rgb.shape[:2]
        x, y, fw, fh = face[0], face[1], face[2], face[3]
        # Expand the box symmetrically.
        cx, cy = x + fw / 2.0, y + fh / 2.0
        side = max(fw, fh) * (1.0 + self.expand)
        x0 = int(round(cx - side / 2.0))
        y0 = int(round(cy - side / 2.0))
        x1 = int(round(cx + side / 2.0))
        y1 = int(round(cy + side / 2.0))
        # Clamp to image bounds.
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            return None
        crop = rgb[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        return cv2.resize(crop, (self.out_size, self.out_size), interpolation=cv2.INTER_AREA)


def _to_rgb_array(image) -> np.ndarray | None:
    """Coerce a PIL image / numpy array into a contiguous uint8 RGB array."""
    if image is None:
        return None
    if isinstance(image, np.ndarray):
        arr = image
    else:
        # Assume PIL.Image
        try:
            arr = np.array(image.convert("RGB"))
        except Exception:  # noqa: BLE001
            return None
    if arr.ndim == 2:
        arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return None
    return np.ascontiguousarray(arr[:, :, :3].astype(np.uint8))
