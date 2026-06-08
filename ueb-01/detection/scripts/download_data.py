#!/usr/bin/env python3
"""Download the FairFace dataset via HuggingFace ``datasets`` and cache it.

FairFace provides aligned face images with an ``age`` string bin, a ``gender``
("Male"/"Female") and a PIL ``image`` column. We try the padded "1.25" config
first, then "0.25", then the default config, and cache to ``detection/.data``.

This stage does NOT crop or relabel -- it just materializes the dataset (or a
capped subset) into the HF cache and prints the class distribution so you can
eyeball balance before the expensive ``prepare.py`` pass.

Usage::

    python scripts/download_data.py [--subset N] [--splits train test]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from common import (
    DATA_DIR,
    map_age_to_band,
    map_gender_to_label,
    seed_everything,
    setup_logging,
)

LOG = setup_logging("download_data")

# Config names to try in order. FairFace on the Hub is exposed under
# "HuggingFaceM4/FairFace" with "1.25" (padding=1.25) and "0.25" configs.
_CONFIG_CANDIDATES = ["1.25", "0.25", None]
_DATASET_ID = "HuggingFaceM4/FairFace"


def _resolve_field(example: dict, *names: str):
    """Return the first present field among ``names`` from an example dict."""
    for n in names:
        if n in example:
            return example[n]
    return None


def load_fairface(subset: int | None, splits: list[str]):
    """Load FairFace, trying config candidates until one works.

    Returns a tuple ``(dataset_dict, config_used)``. Applies a per-split cap
    via ``--subset`` using ``.select`` so we don't stream the entire dataset
    when developing.
    """
    from datasets import load_dataset

    last_err: Exception | None = None
    for cfg in _CONFIG_CANDIDATES:
        try:
            if cfg is None:
                LOG.info("Trying load_dataset(%s) [default config]", _DATASET_ID)
                ds = load_dataset(_DATASET_ID, cache_dir=str(DATA_DIR))
            else:
                LOG.info("Trying load_dataset(%s, %r)", _DATASET_ID, cfg)
                ds = load_dataset(_DATASET_ID, cfg, cache_dir=str(DATA_DIR))
            LOG.info("Loaded FairFace with config=%r. Splits: %s", cfg, list(ds.keys()))
            ds = _maybe_subset(ds, subset, splits)
            return ds, (cfg or "default")
        except Exception as exc:  # noqa: BLE001
            LOG.warning("Config %r failed: %s", cfg, exc)
            last_err = exc
    raise RuntimeError(f"Could not load FairFace with any config: {last_err}")


def _maybe_subset(ds, subset: int | None, splits: list[str]):
    """Cap each requested split to ``subset`` rows (if given)."""
    if subset is None:
        return ds
    for split in list(ds.keys()):
        if splits and split not in splits:
            continue
        n = min(subset, len(ds[split]))
        ds[split] = ds[split].select(range(n))
        LOG.info("Capped split %r to %d rows", split, n)
    return ds


def _decode_label(feature, value):
    """Convert a ClassLabel int to its string name when needed."""
    try:
        # datasets ClassLabel exposes int2str
        if hasattr(feature, "int2str") and isinstance(value, int):
            return feature.int2str(value)
    except Exception:  # noqa: BLE001
        pass
    return value


def print_distribution(ds, splits: list[str]) -> None:
    """Print per-split age-band and gender distributions after mapping."""
    for split in ds.keys():
        if splits and split not in splits:
            continue
        feats = ds[split].features
        age_feat = feats.get("age")
        gender_feat = feats.get("gender")
        age_counts: Counter = Counter()
        gender_counts: Counter = Counter()
        raw_age_counts: Counter = Counter()
        dropped = 0
        # Only iterate the label columns (avoid decoding images).
        cols = [c for c in ("age", "gender") if c in ds[split].column_names]
        for ex in ds[split].select(range(len(ds[split]))).with_format(
            "python", columns=cols
        ):
            age_raw = _decode_label(age_feat, _resolve_field(ex, "age"))
            gen_raw = _decode_label(gender_feat, _resolve_field(ex, "gender"))
            raw_age_counts[str(age_raw)] += 1
            band = map_age_to_band(age_raw)
            glabel = map_gender_to_label(gen_raw)
            if band is None or glabel is None:
                dropped += 1
                continue
            age_counts[band] += 1
            gender_counts[glabel] += 1
        LOG.info("=== Split %r (n=%d) ===", split, len(ds[split]))
        LOG.info("  raw age bins: %s", dict(sorted(raw_age_counts.items())))
        LOG.info("  age bands   : %s", dict(age_counts))
        LOG.info("  genders     : %s", dict(gender_counts))
        if dropped:
            LOG.warning("  %d rows had unmappable age/gender labels", dropped)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--subset",
        type=int,
        default=None,
        help="Cap rows per split (for fast iteration). Default: full dataset.",
    )
    parser.add_argument(
        "--splits",
        nargs="*",
        default=["train", "validation", "test"],
        help="Which splits to consider for the distribution printout.",
    )
    args = parser.parse_args()

    seed_everything()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        ds, cfg = load_fairface(args.subset, args.splits)
    except Exception as exc:  # noqa: BLE001
        LOG.error("FairFace download failed: %s", exc)
        return 1

    LOG.info("FairFace ready (config=%s) cached under %s", cfg, DATA_DIR)
    print_distribution(ds, args.splits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
