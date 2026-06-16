"""On-device audience classification pipeline.

Pure, deterministic inference core that runs **in-process** inside the App (no
sidecar, no HTTP). It is fed a camera JPEG frame and returns a scene-level
audience dict.

Flow: JPEG bytes -> cv2.imdecode -> YuNet face detection -> per-face crop ->
ONNX classify (age band + gender) -> aggregate to a scene-level target group.

All model-shape facts (input size, normalization, label names, output names,
thresholds, target-group rules) are read from ``labels.json`` and are NOT
hardcoded here.

The heavy deps (``cv2``, ``onnxruntime``) are imported at module load. The
composition root constructs :class:`AudiencePipeline` behind a guarded import so
a board whose App environment lacks those wheels degrades to the static
audience classifier instead of crashing (see ``main.py``).
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort

# Cap the inference thread pools so a classify burst can't grab all of the
# board's (4) cores. ONNX Runtime and OpenCV both default to one thread per
# core; left uncapped they momentarily starve the brick's camera-feed thread,
# which stalls the JPEG stream to the EI runner and crashes its capture pipeline
# ("Capture process failed with code 1" -> runner restart -> broken pipe -> the
# debug preview freezes/blanks). 2 leaves ~2 cores for the feed + EI runner;
# tune via AUDIENCE_INFER_THREADS (try 1 if the runner still crashes).
_INFER_THREADS = max(1, int(os.environ.get("AUDIENCE_INFER_THREADS", "2")))

LABELS_FILE = "labels.json"
CLASSIFIER_FILE = "audience_classifier.onnx"
YUNET_FILE = "face_detection_yunet_2023mar.onnx"

# Model files ship with the App under ``audience/models/`` and sync to the board
# via ``cli/rsync.sh``. Overridable with ``AUDIENCE_MODEL_DIR`` for tests / a
# custom board layout.
DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")


def _softmax(logits: np.ndarray) -> np.ndarray:
    """Numerically stable softmax over the last axis."""
    logits = logits - np.max(logits, axis=-1, keepdims=True)
    exp = np.exp(logits)
    return exp / np.sum(exp, axis=-1, keepdims=True)


class AudiencePipeline:
    """Loads the labels + both models and classifies camera frames.

    Parameters
    ----------
    model_dir:
        Directory holding ``labels.json``, ``audience_classifier.onnx`` and
        ``face_detection_yunet_2023mar.onnx``. Defaults to the ``AUDIENCE_MODEL_DIR``
        env var, then the bundled ``audience/models`` directory.
    """

    def __init__(self, model_dir: str | None = None) -> None:
        self.model_dir = model_dir or os.environ.get("AUDIENCE_MODEL_DIR", DEFAULT_MODEL_DIR)

        labels_path = os.path.join(self.model_dir, LABELS_FILE)
        with open(labels_path, "r", encoding="utf-8") as fh:
            self.labels: dict[str, Any] = json.load(fh)

        # --- model contract pulled from labels.json (never hardcoded) ---
        self.input_size: int = int(self.labels["input_size"])
        self.mean = np.asarray(self.labels["mean"], dtype=np.float32).reshape(3, 1, 1)
        self.std = np.asarray(self.labels["std"], dtype=np.float32).reshape(3, 1, 1)
        self.color_order: str = self.labels.get("color_order", "RGB")
        self.age_bands: list[str] = list(self.labels["age_bands"])
        self.genders: list[str] = list(self.labels["genders"])
        self.onnx_input: str = self.labels["onnx_input"]
        self.onnx_outputs: dict[str, str] = self.labels["onnx_outputs"]
        self.child_band: str = self.labels["child_band"]
        self.face_score_threshold: float = float(
            self.labels.get("thresholds", {}).get("face_score", 0.6)
        )
        self.rules: dict[str, Any] = self.labels["target_group_rules"]

        # --- ONNX classifier session ---
        # Thread-capped (see _INFER_THREADS) so inference leaves cores free for
        # the camera feed / EI runner.
        classifier_path = os.path.join(self.model_dir, CLASSIFIER_FILE)
        so = ort.SessionOptions()
        so.intra_op_num_threads = _INFER_THREADS
        so.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            classifier_path, sess_options=so, providers=["CPUExecutionProvider"]
        )

        # OpenCV (YuNet detect / imdecode / resize) also defaults to all cores.
        cv2.setNumThreads(_INFER_THREADS)

        # --- YuNet face detector ---
        yunet_path = os.path.join(self.model_dir, YUNET_FILE)
        # Input size is reset per-frame in classify(); 320x320 is just a seed.
        self.face_detector = cv2.FaceDetectorYN.create(
            model=yunet_path,
            config="",
            input_size=(320, 320),
            score_threshold=self.face_score_threshold,
            nms_threshold=0.3,
            top_k=5000,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def classify(self, jpeg_bytes: bytes) -> dict[str, Any]:
        """Classify a full-frame JPEG into an audience dict.

        Never raises on a normal frame (including a no-face frame). Only a
        genuinely undecodable buffer raises ``ValueError``.
        """
        buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("could not decode JPEG bytes")

        h, w = frame.shape[:2]
        self.face_detector.setInputSize((w, h))
        _, detections = self.face_detector.detect(frame)

        if detections is None or len(detections) == 0:
            return self._empty()

        faces: list[dict[str, Any]] = []
        crops: list[np.ndarray] = []
        boxes: list[list[int]] = []

        for det in detections:
            score = float(det[14])
            if score < self.face_score_threshold:
                continue
            x, y, bw, bh = det[0], det[1], det[2], det[3]
            box = self._expand_box(x, y, bw, bh, w, h, factor=0.20)
            bx, by, bbw, bbh = box
            crop = frame[by : by + bbh, bx : bx + bbw]
            if crop.size == 0:
                continue
            crops.append(self._preprocess(crop))
            boxes.append(box)

        if not crops:
            return self._empty()

        batch = np.stack(crops, axis=0).astype(np.float32)
        outputs = self.session.run(
            [self.onnx_outputs["age"], self.onnx_outputs["gender"]],
            {self.onnx_input: batch},
        )
        age_logits, gender_logits = outputs[0], outputs[1]
        age_probs = _softmax(np.asarray(age_logits, dtype=np.float32))
        gender_probs = _softmax(np.asarray(gender_logits, dtype=np.float32))

        for i, box in enumerate(boxes):
            age_idx = int(np.argmax(age_probs[i]))
            gender_idx = int(np.argmax(gender_probs[i]))
            faces.append(
                {
                    "age_band": self.age_bands[age_idx],
                    "gender": self.genders[gender_idx],
                    "age_conf": round(float(age_probs[i][age_idx]), 4),
                    "gender_conf": round(float(gender_probs[i][gender_idx]), 4),
                    "box": box,
                }
            )

        return {
            "people_count": len(faces),
            "faces": faces,
            "target_group": self._aggregate(faces),
            "source": "face-local",
        }

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "people_count": 0,
            "faces": [],
            "target_group": "unknown",
            "source": "face-local",
        }

    @staticmethod
    def _expand_box(
        x: float,
        y: float,
        bw: float,
        bh: float,
        img_w: int,
        img_h: int,
        factor: float,
    ) -> list[int]:
        """Expand a face box by ``factor`` on each side, clamped to the frame."""
        dx = bw * factor
        dy = bh * factor
        nx = int(round(x - dx))
        ny = int(round(y - dy))
        nx2 = int(round(x + bw + dx))
        ny2 = int(round(y + bh + dy))
        nx = max(0, nx)
        ny = max(0, ny)
        nx2 = min(img_w, nx2)
        ny2 = min(img_h, ny2)
        return [nx, ny, max(0, nx2 - nx), max(0, ny2 - ny)]

    def _preprocess(self, crop_bgr: np.ndarray) -> np.ndarray:
        """Resize -> color order -> /255 -> normalize -> NCHW float32 (single)."""
        resized = cv2.resize(
            crop_bgr, (self.input_size, self.input_size), interpolation=cv2.INTER_LINEAR
        )
        if self.color_order.upper() == "RGB":
            resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        arr = resized.astype(np.float32) / 255.0
        arr = np.transpose(arr, (2, 0, 1))  # HWC -> CHW
        arr = (arr - self.mean) / self.std
        return arr.astype(np.float32)

    def _aggregate(self, faces: list[dict[str, Any]]) -> str:
        """Scene-level target group from per-face results.

        Rules (from labels.json target_group_rules):
          1. any child -> ``child_any`` label
          2. else dominant (most frequent age_band, then its majority gender)
             keyed ``"<band>|<gender>"`` in the ``dominant`` table
          3. else ``default``
        """
        if not faces:
            return "unknown"

        # Rule 1: any child present.
        if any(f["age_band"] == self.child_band for f in faces):
            return self.rules.get("child_any", self.rules.get("default", "unknown"))

        # Rule 2: dominant age band (most frequent), tie-broken deterministically.
        band_counts = Counter(f["age_band"] for f in faces)
        max_count = max(band_counts.values())
        dominant_bands = sorted(b for b, c in band_counts.items() if c == max_count)
        dominant_band = dominant_bands[0]

        band_faces = [f for f in faces if f["age_band"] == dominant_band]
        gender_counts = Counter(f["gender"] for f in band_faces)
        max_g = max(gender_counts.values())
        majority_genders = sorted(g for g, c in gender_counts.items() if c == max_g)
        majority_gender = majority_genders[0]

        key = f"{dominant_band}|{majority_gender}"
        dominant_table = self.rules.get("dominant", {})
        if key in dominant_table:
            return dominant_table[key]

        return self.rules.get("default", "unknown")
