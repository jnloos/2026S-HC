#!/usr/bin/env python3
"""Download the shared YuNet face-detector ONNX into ``detection/models/``.

The YuNet model (``face_detection_yunet_2023mar.onnx``) is fetched from the
OpenCV Zoo raw GitHub URL. It is shared with the App (face detection at
inference time) and used here by ``prepare.py`` to crop aligned faces.

Idempotent: skips the download if the file already exists (use ``--force`` to
re-download).

Usage::

    python scripts/fetch_models.py [--force]
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

from common import YUNET_PATH, YUNET_URL, setup_logging

LOG = setup_logging("fetch_models")

# YuNet 2023mar is roughly 230 KB; reject obviously-truncated downloads.
MIN_EXPECTED_BYTES = 50_000


def download(url: str, dest: Path) -> None:
    """Stream ``url`` to ``dest`` atomically (via a ``.part`` temp file)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    LOG.info("Downloading %s", url)
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (trusted URL)
        data = resp.read()
    if len(data) < MIN_EXPECTED_BYTES:
        raise RuntimeError(
            f"Downloaded file is suspiciously small ({len(data)} bytes); aborting."
        )
    tmp.write_bytes(data)
    tmp.replace(dest)
    LOG.info("Saved %s (%d bytes)", dest, len(data))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the model already exists.",
    )
    args = parser.parse_args()

    if YUNET_PATH.exists() and not args.force:
        LOG.info(
            "YuNet already present at %s (%d bytes) -- skipping. Use --force to redownload.",
            YUNET_PATH,
            YUNET_PATH.stat().st_size,
        )
        return 0

    try:
        download(YUNET_URL, YUNET_PATH)
    except Exception as exc:  # noqa: BLE001
        LOG.error("Failed to download YuNet: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
