#!/usr/bin/env python3
"""Train the two-headed MobileNetV3-small audience classifier on face crops.

Reads ``artifacts/crops/labels.csv`` (from ``prepare.py``), builds a
class-balanced sampler over the AGE head (the minority/child signal we most
care about), trains with a summed per-head CrossEntropy, freezes the backbone
for the first few epochs then unfreezes at a lower LR. Saves the best
checkpoint (by macro child-band recall, fallback balanced accuracy) to
``artifacts/best.pt`` and writes ``artifacts/metrics.json`` with per-class
precision/recall + confusion matrices for both heads (via sklearn).

Usage::

    python scripts/train.py --epochs 12 --batch-size 64 --lr 1e-3 \
        --input-size 112 --max-train 20000 --val-frac 0.1
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, WeightedRandomSampler

from common import (
    AGE_BANDS,
    AGE_BAND_TO_IDX,
    ARTIFACTS_DIR,
    BEST_CKPT_PATH,
    CROPS_DIR,
    GENDERS,
    INPUT_SIZE,
    METRICS_PATH,
    SEED,
    seed_everything,
    setup_logging,
    write_json,
)
from dataset import CropDataset, load_rows
from model import AudienceClassifier

LOG = setup_logging("train")
CHILD_IDX = AGE_BAND_TO_IDX["child"]


# --------------------------------------------------------------------------- #
# Sampler / splitting
# --------------------------------------------------------------------------- #
def stratified_split(rows: list[dict], val_frac: float, seed: int):
    """Split rows into train/val, stratified by age band."""
    rng = np.random.default_rng(seed)
    by_band: dict[str, list] = {}
    for r in rows:
        by_band.setdefault(r["age_band"], []).append(r)
    train_rows, val_rows = [], []
    for band, items in by_band.items():
        idx = np.arange(len(items))
        rng.shuffle(idx)
        n_val = max(1, int(round(len(items) * val_frac))) if len(items) > 1 else 0
        val_idx = set(idx[:n_val].tolist())
        for i, it in enumerate(items):
            (val_rows if i in val_idx else train_rows).append(it)
    rng.shuffle(train_rows)
    rng.shuffle(val_rows)
    return train_rows, val_rows


def build_age_balanced_sampler(train_ds: CropDataset) -> WeightedRandomSampler:
    """Weight each sample by inverse age-band frequency to balance the age head."""
    targets = np.asarray(train_ds.age_targets)
    counts = np.bincount(targets, minlength=len(AGE_BANDS)).astype(np.float64)
    counts[counts == 0] = 1.0
    class_w = 1.0 / counts
    sample_w = class_w[targets]
    return WeightedRandomSampler(
        weights=torch.as_tensor(sample_w, dtype=torch.double),
        num_samples=len(sample_w),
        replacement=True,
    )


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def evaluate(model, loader, device):
    """Run the model over ``loader`` and return predictions/targets for both heads."""
    model.eval()
    age_pred, age_true, gen_pred, gen_true = [], [], [], []
    with torch.no_grad():
        for x, age_t, gen_t in loader:
            x = x.to(device)
            age_logits, gen_logits = model(x)
            age_pred.extend(age_logits.argmax(1).cpu().tolist())
            gen_pred.extend(gen_logits.argmax(1).cpu().tolist())
            age_true.extend(age_t.tolist())
            gen_true.extend(gen_t.tolist())
    return (
        np.array(age_true),
        np.array(age_pred),
        np.array(gen_true),
        np.array(gen_pred),
    )


def head_metrics(y_true, y_pred, labels, class_names) -> dict:
    """Per-class precision/recall/f1 + confusion matrix + balanced acc."""
    from sklearn.metrics import (
        balanced_accuracy_score,
        confusion_matrix,
        precision_recall_fscore_support,
    )

    p, r, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    per_class = {}
    for i, name in enumerate(class_names):
        per_class[name] = {
            "precision": float(p[i]),
            "recall": float(r[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
    bal_acc = (
        float(balanced_accuracy_score(y_true, y_pred)) if len(y_true) else 0.0
    )
    return {
        "per_class": per_class,
        "confusion_matrix": cm.tolist(),
        "labels": class_names,
        "balanced_accuracy": bal_acc,
        "macro_recall": float(np.mean(r)) if len(r) else 0.0,
    }


# --------------------------------------------------------------------------- #
# Training loop
# --------------------------------------------------------------------------- #
def train(args) -> int:
    seed_everything(SEED)
    torch.set_num_threads(os.cpu_count() or 1)
    device = torch.device("cpu")
    LOG.info("Device=%s threads=%d", device, torch.get_num_threads())

    csv_path = CROPS_DIR / "labels.csv"
    if not csv_path.exists():
        LOG.error("Missing %s -- run prepare.py first.", csv_path)
        return 1
    rows = load_rows(csv_path)
    if args.max_train:
        rows = rows[: args.max_train]
    LOG.info("Loaded %d labeled crops", len(rows))

    train_rows, val_rows = stratified_split(rows, args.val_frac, SEED)
    LOG.info("Split: train=%d val=%d", len(train_rows), len(val_rows))

    train_ds = CropDataset(train_rows, input_size=args.input_size, augment=True)
    val_ds = CropDataset(val_rows, input_size=args.input_size, augment=False)

    sampler = build_age_balanced_sampler(train_ds)
    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        sampler=sampler,
        num_workers=args.num_workers,
        drop_last=False,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )

    model = AudienceClassifier(pretrained=True).to(device)
    criterion = nn.CrossEntropyLoss()

    # Phase 1: backbone frozen.
    model.set_backbone_requires_grad(False)
    optimizer = _make_optimizer(model, args.lr, frozen=True)

    best_score = -1.0
    best_metrics: dict | None = None

    for epoch in range(1, args.epochs + 1):
        if epoch == args.freeze_epochs + 1:
            LOG.info("Unfreezing backbone at epoch %d (lr=%g)", epoch, args.lr * 0.1)
            model.set_backbone_requires_grad(True)
            optimizer = _make_optimizer(model, args.lr * 0.1, frozen=False)

        model.train()
        running = 0.0
        for x, age_t, gen_t in train_loader:
            x, age_t, gen_t = x.to(device), age_t.to(device), gen_t.to(device)
            optimizer.zero_grad()
            age_logits, gen_logits = model(x)
            loss = criterion(age_logits, age_t) + criterion(gen_logits, gen_t)
            loss.backward()
            optimizer.step()
            running += loss.item() * x.size(0)
        train_loss = running / max(1, len(train_ds))

        # Validate.
        age_true, age_pred, gen_true, gen_pred = evaluate(model, val_loader, device)
        age_m = head_metrics(age_true, age_pred, list(range(len(AGE_BANDS))), AGE_BANDS)
        gen_m = head_metrics(gen_true, gen_pred, list(range(len(GENDERS))), GENDERS)

        child_recall = age_m["per_class"]["child"]["recall"]
        score = child_recall if age_m["per_class"]["child"]["support"] else age_m[
            "balanced_accuracy"
        ]
        LOG.info(
            "epoch %2d | loss=%.4f | child_recall=%.3f | age_balacc=%.3f | gender_balacc=%.3f | score=%.3f",
            epoch,
            train_loss,
            child_recall,
            age_m["balanced_accuracy"],
            gen_m["balanced_accuracy"],
            score,
        )

        if score > best_score:
            best_score = score
            best_metrics = {
                "epoch": epoch,
                "selection_score": score,
                "selection_criterion": "child_recall_fallback_balacc",
                "train_loss": train_loss,
                "age": age_m,
                "gender": gen_m,
            }
            _save_checkpoint(model, args, epoch, best_metrics)
            LOG.info("  -> new best (score=%.3f), checkpoint saved", score)

    if best_metrics is None:
        LOG.error("No epochs completed; nothing saved.")
        return 1

    write_json(METRICS_PATH, best_metrics)
    LOG.info("Best score=%.3f at epoch %d", best_score, best_metrics["epoch"])
    LOG.info("Wrote metrics to %s and checkpoint to %s", METRICS_PATH, BEST_CKPT_PATH)
    return 0


def _make_optimizer(model, lr, frozen: bool):
    params = [p for p in model.parameters() if p.requires_grad]
    return torch.optim.AdamW(params, lr=lr, weight_decay=1e-4)


def _save_checkpoint(model, args, epoch, metrics) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "epoch": epoch,
            "input_size": args.input_size,
            "age_bands": AGE_BANDS,
            "genders": GENDERS,
            "metrics": metrics,
            "arch": "mobilenet_v3_small_two_head",
        },
        BEST_CKPT_PATH,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--input-size", type=int, default=INPUT_SIZE)
    parser.add_argument(
        "--max-train", type=int, default=None, help="Cap total labeled rows used."
    )
    parser.add_argument("--val-frac", type=float, default=0.1)
    parser.add_argument(
        "--freeze-epochs",
        type=int,
        default=3,
        help="Epochs to keep the backbone frozen before unfreezing.",
    )
    parser.add_argument("--num-workers", type=int, default=2)
    args = parser.parse_args()

    if args.input_size != INPUT_SIZE:
        LOG.warning(
            "input_size=%d differs from frozen spec %d; ONNX export expects %d.",
            args.input_size,
            INPUT_SIZE,
            INPUT_SIZE,
        )
    return train(args)


if __name__ == "__main__":
    sys.exit(main())
