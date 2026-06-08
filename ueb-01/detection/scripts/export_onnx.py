#!/usr/bin/env python3
"""Export the best checkpoint to ONNX and write labels.json + model_card.md.

Loads ``artifacts/best.pt``, rebuilds the two-headed MobileNetV3-small, and
exports to ``models/audience_classifier.onnx`` with the FROZEN contract:

  * input  : ``input``        shape [N,3,112,112], dynamic batch N
  * outputs: ``age_logits``   [N,5]
             ``gender_logits``[N,2]
  * opset  : >= 13

Also writes ``models/labels.json`` (exact structure the inference pipeline reads) and a
``models/model_card.md``. Optional ``--int8`` applies dynamic quantization to
``models/audience_classifier.int8.onnx``.

Usage::

    python scripts/export_onnx.py [--int8] [--opset 13]
"""

from __future__ import annotations

import argparse
import json
import sys

import torch

from common import (
    AGE_BANDS,
    BEST_CKPT_PATH,
    GENDERS,
    INPUT_SIZE,
    LABELS_PATH,
    MEAN,
    METRICS_PATH,
    MODEL_CARD_PATH,
    ONNX_AGE_OUTPUT,
    ONNX_GENDER_OUTPUT,
    ONNX_INPUT_NAME,
    ONNX_INT8_PATH,
    ONNX_MODEL_PATH,
    STD,
    labels_json,
    seed_everything,
    setup_logging,
    write_json,
)
from model import AudienceClassifier

LOG = setup_logging("export_onnx")


def load_model(input_size: int) -> AudienceClassifier:
    """Rebuild the model and load the best checkpoint weights."""
    if not BEST_CKPT_PATH.exists():
        raise FileNotFoundError(
            f"No checkpoint at {BEST_CKPT_PATH}. Run train.py first."
        )
    ckpt = torch.load(BEST_CKPT_PATH, map_location="cpu", weights_only=False)
    model = AudienceClassifier(pretrained=False)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    ck_size = ckpt.get("input_size", input_size)
    if ck_size != input_size:
        LOG.warning("Checkpoint input_size=%d, exporting at %d", ck_size, input_size)
    return model


def export(model, input_size: int, opset: int) -> None:
    """Trace + export to ONNX with dynamic batch and the frozen IO names."""
    ONNX_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 3, input_size, input_size, dtype=torch.float32)
    export_kwargs = dict(
        input_names=[ONNX_INPUT_NAME],
        output_names=[ONNX_AGE_OUTPUT, ONNX_GENDER_OUTPUT],
        dynamic_axes={
            ONNX_INPUT_NAME: {0: "batch"},
            ONNX_AGE_OUTPUT: {0: "batch"},
            ONNX_GENDER_OUTPUT: {0: "batch"},
        },
        opset_version=opset,
        do_constant_folding=True,
    )
    # torch>=2.x defaults to the dynamo exporter (needs onnxscript). Pin the
    # stable TorchScript exporter so dynamic_axes/opset behave as specified;
    # fall back gracefully on older torch that lacks the ``dynamo`` kwarg.
    try:
        torch.onnx.export(model, dummy, str(ONNX_MODEL_PATH), dynamo=False, **export_kwargs)
    except TypeError:
        torch.onnx.export(model, dummy, str(ONNX_MODEL_PATH), **export_kwargs)
    LOG.info("Exported ONNX -> %s", ONNX_MODEL_PATH)


def verify_onnx() -> None:
    """Structural check of the exported graph IO names/shapes."""
    import onnx

    m = onnx.load(str(ONNX_MODEL_PATH))
    onnx.checker.check_model(m)
    inames = [i.name for i in m.graph.input]
    onames = [o.name for o in m.graph.output]
    LOG.info("ONNX inputs=%s outputs=%s", inames, onames)
    assert ONNX_INPUT_NAME in inames, f"missing input {ONNX_INPUT_NAME}"
    assert ONNX_AGE_OUTPUT in onames, f"missing output {ONNX_AGE_OUTPUT}"
    assert ONNX_GENDER_OUTPUT in onames, f"missing output {ONNX_GENDER_OUTPUT}"


def quantize_int8() -> None:
    """Apply dynamic int8 quantization for a smaller on-device model."""
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(
        model_input=str(ONNX_MODEL_PATH),
        model_output=str(ONNX_INT8_PATH),
        weight_type=QuantType.QInt8,
    )
    LOG.info("Wrote int8 ONNX -> %s", ONNX_INT8_PATH)


def write_model_card() -> None:
    """Write a model card summarizing dataset, license, mapping, ethics."""
    metrics_summary = "Metrics not available (best.pt produced without metrics.json)."
    if METRICS_PATH.exists():
        try:
            m = json.loads(METRICS_PATH.read_text())
            age = m.get("age", {})
            gen = m.get("gender", {})
            child = age.get("per_class", {}).get("child", {})
            metrics_summary = (
                f"- Selected epoch: {m.get('epoch')}\n"
                f"- Age head balanced accuracy: {age.get('balanced_accuracy', 0):.3f}\n"
                f"- Age macro recall: {age.get('macro_recall', 0):.3f}\n"
                f"- Child-band recall (priority metric): {child.get('recall', 0):.3f}\n"
                f"- Gender head balanced accuracy: {gen.get('balanced_accuracy', 0):.3f}\n"
            )
        except Exception:  # noqa: BLE001
            pass

    card = f"""# Audience Classifier (on-device demographic estimator)

Two-headed **MobileNetV3-small** estimating a coarse **age band** and a
**binary gender** from an aligned 112x112 face crop. Trained for the
ARDU-DigSig-Prototype detection pipeline; exported to ONNX for the
on-device inference pipeline.

## Dataset
- **FairFace** (HuggingFace `HuggingFaceM4/FairFace`).
- **License: CC BY 4.0** (FairFace). Attribution: Karkkainen & Joo, "FairFace:
  Face Attribute Dataset for Balanced Race, Gender, and Age".

## Label mapping (frozen spec)
- Age bands (output order): {AGE_BANDS}
- Genders (output order): {GENDERS}
- FairFace age bin -> band:
  - child: `0-2`, `3-9`
  - teen: `10-19`
  - young-adult: `20-29`
  - adult: `30-39`, `40-49`, `50-59`
  - senior: `60-69`, `more than 70`
- FairFace gender `Male`/`Female` -> `male`/`female`.

## Input / preprocessing
- Input tensor `input`: `[N, 3, {INPUT_SIZE}, {INPUT_SIZE}]`, RGB.
- `/255`, then normalize mean={MEAN}, std={STD} (ImageNet).
- Face crop produced by YuNet (`face_detection_yunet_2023mar.onnx`), largest
  face, box expanded ~20%.

## Outputs
- `age_logits`: `[N, 5]` (argmax over age bands above).
- `gender_logits`: `[N, 2]` (argmax over genders above).

## Metrics (validation, best checkpoint)
{metrics_summary}

## ETHICS / limitations
- These are **estimates, not ground truth.** Age band and gender are inferred
  from facial appearance and will be wrong for a meaningful fraction of people.
  Do not use for identity, access, eligibility, or any consequential decision
  about an individual.
- **Binary gender is a modeling limitation**, not a statement about gender. The
  FairFace label space is binary; this model cannot represent non-binary or
  other gender identities and will mislabel many people.
- Demographic estimators carry known **accuracy disparities across skin tone,
  age and presentation**. FairFace is race-balanced to mitigate this, but
  residual bias remains. Use only for aggregate, non-identifying audience
  signals (e.g. "show family content"), never per-person.
- No images are stored by the on-device pipeline; classification is ephemeral.
"""
    MODEL_CARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_CARD_PATH.write_text(card, encoding="utf-8")
    LOG.info("Wrote model card -> %s", MODEL_CARD_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--opset", type=int, default=13, help="ONNX opset (>=13).")
    parser.add_argument("--input-size", type=int, default=INPUT_SIZE)
    parser.add_argument(
        "--int8",
        action="store_true",
        help="Also write a dynamically-quantized int8 ONNX.",
    )
    args = parser.parse_args()

    if args.opset < 13:
        LOG.error("opset must be >= 13 (got %d)", args.opset)
        return 1

    seed_everything()
    try:
        model = load_model(args.input_size)
    except FileNotFoundError as exc:
        LOG.error("%s", exc)
        return 1

    export(model, args.input_size, args.opset)
    verify_onnx()

    write_json(LABELS_PATH, labels_json())
    LOG.info("Wrote labels.json -> %s", LABELS_PATH)
    write_model_card()

    if args.int8:
        try:
            quantize_int8()
        except Exception as exc:  # noqa: BLE001
            LOG.error("int8 quantization failed: %s", exc)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
