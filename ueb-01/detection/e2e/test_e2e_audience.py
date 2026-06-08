#!/usr/bin/env python3
"""End-to-end proof: demographics -> target_group -> content WITHOUT a camera.

This script injects fixed JPEG fixtures into the *real* selection pipeline and
verifies that the audience signal actually steers content selection. It chains
the in-process inference with the CMS exactly as the running board would:

    JPEG fixture
        -> AudiencePipeline.classify()           (in-process face inference -> audience dict)
        -> POST {api}/pools/{id}/choose-by-context   (V2 hybrid -> Claude picks)
        -> chosen content id

The audience dict is placed under the ``"audience"`` key of the open-shaped V2
context envelope — the same shape the board builds in
``arduino/python/pipeline/context.py`` (``{"trigger": ..., "audience": ...}``).
The V2 endpoint accepts any JSON object and flows every key into the Claude
prompt, so no schema change is needed.

What this proves (and why it needs no camera/child):
  * The in-process pipeline turns a face image into a demographic/target_group dict.
  * That dict, sent as context, makes the CMS choose the *demographically
    appropriate* content. For the bakery seed, a child face must select
    content #4 "Kinder-Naschstation" (whose description says "NUR anzeigen,
    wenn Kinder ... erkannt werden"), while an adult face must NOT.

PRECONDITIONS (none of which this script sets up):
  * API up with a Claude key + seeded bakery pool:
        cd api && cp .env.xmpl .env   # set ANTHROPIC_API_KEY=...
        digsig db upgrade && digsig seed bakery
        ./cli/dev.sh up               # (or uvicorn ... --port 8000)
  * The ONNX models present (bundled at arduino/python/audience/models/, or set
    AUDIENCE_MODEL_DIR) and cv2 + onnxruntime importable (detection/.venv has them).
  * Fixtures present under --fixtures (default arduino/python/tests/fixtures):
        child.jpg, young-adult_female.jpg   (produced by make_fixtures.py)

Exit code is non-zero on any assertion or transport failure, so this doubles as
a CI/smoke gate. It is import-safe, so ``pytest`` will also collect
``test_e2e_audience`` if run with the API up (it self-skips otherwise).

API CONTRACT (verified against api/app/api/routers/pools.py +
api/app/services/selection.py):
  * Endpoint : POST /pools/{pool_id}/choose-by-context
  * Body     : a raw JSON object (RootModel) — NOT wrapped; any keys allowed.
  * Response : {"pool_id", "chosen_id", "name", "description", "html",
               "reasoning"}.  The chosen content id field is **chosen_id**.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - clearer message than a raw traceback
    print(
        "ERROR: this script needs `requests` (pip install requests).",
        file=sys.stderr,
    )
    raise

# Make the App's in-process inference importable (arduino/python on sys.path).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_PYTHON = _REPO_ROOT / "arduino" / "python"
if str(_APP_PYTHON) not in sys.path:
    sys.path.insert(0, str(_APP_PYTHON))

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #
DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_POOL_ID = 1  # the bakery seed creates exactly one pool (#1) on a fresh DB
# The bakery seed inserts six contents in order; #4 is "Kinder-Naschstation".
CHILD_CONTENT_ID = 4
CHILD_CONTENT_NAME = "Kinder-Naschstation"

# Fixtures (produced by make_fixtures.py) — see arduino/python/tests/test_inference.py.
CHILD_FIXTURE = "child.jpg"
ADULT_FIXTURE = "young-adult_female.jpg"

DEFAULT_FIXTURES_DIR = _REPO_ROOT / "arduino" / "python" / "tests" / "fixtures"


class E2EError(RuntimeError):
    """Raised on any transport/contract failure (vs. an assertion mismatch)."""


@dataclass
class Run:
    """One fixture's full classify -> choose trip."""

    fixture: str
    audience: dict[str, Any]
    chosen_id: int
    chosen_name: str
    reasoning: str
    full_choice: dict[str, Any]


# --------------------------------------------------------------------------- #
# Inference (in-process) + service call
# --------------------------------------------------------------------------- #
def make_pipeline():
    """Construct the in-process AudiencePipeline, raising E2EError on failure."""
    try:
        from audience.inference import AudiencePipeline
        return AudiencePipeline()
    except Exception as e:  # noqa: BLE001 — surface a clear setup error
        raise E2EError(
            f"could not build the in-process inference pipeline: {e}\n"
            "  -> need cv2 + onnxruntime and the ONNX models (bundled at "
            "arduino/python/audience/models/ or set AUDIENCE_MODEL_DIR)."
        ) from e


def choose_by_context(
    api_url: str,
    pool_id: int,
    audience: dict[str, Any],
    timeout: float = 120.0,
) -> dict[str, Any]:
    """POST the V2 hybrid context envelope -> ChoiceOut dict.

    Mirrors the board's PipelineContext.to_dict(): the audience dict goes under
    the ``"audience"`` key. The endpoint accepts any object, so this is the
    minimal load-bearing envelope.
    """
    url = f"{api_url.rstrip('/')}/pools/{pool_id}/choose-by-context"
    body = {"audience": audience}
    try:
        resp = requests.post(url, json=body, timeout=timeout)
    except requests.RequestException as e:
        raise E2EError(f"API unreachable at {url}: {e}") from e
    if resp.status_code != 200:
        raise E2EError(f"{url} returned HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        return resp.json()
    except ValueError as e:
        raise E2EError(f"{url} returned non-JSON body: {resp.text[:300]}") from e


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_fixture(
    *,
    pipeline,
    api_url: str,
    pool_id: int,
    fixtures_dir: Path,
    fixture: str,
) -> Run:
    """Classify a fixture then ask the CMS to choose; return the combined Run."""
    path = fixtures_dir / fixture
    if not path.is_file():
        raise E2EError(
            f"fixture not found: {path}\n"
            "  -> make_fixtures.py produces these under arduino/python/tests/fixtures/."
        )
    jpeg = path.read_bytes()
    audience = pipeline.classify(jpeg)
    choice = choose_by_context(api_url, pool_id, audience)
    return Run(
        fixture=fixture,
        audience=audience,
        chosen_id=int(choice.get("chosen_id", -1)),
        chosen_name=str(choice.get("name", "")),
        reasoning=str(choice.get("reasoning", "")),
        full_choice=choice,
    )


def _print_run(label: str, run: Run) -> None:
    print(f"\n--- {label}: {run.fixture} ---")
    print(f"  audience.target_group = {run.audience.get('target_group')!r}")
    print(f"  audience.people_count = {run.audience.get('people_count')!r}")
    print(f"  source                = {run.audience.get('source')!r}")
    print(f"  -> chosen_id={run.chosen_id}  name={run.chosen_name!r}")
    print(f"     reasoning: {run.reasoning[:300]}")


def _attempt(
    *,
    pipeline,
    api_url: str,
    pool_id: int,
    fixtures_dir: Path,
) -> tuple[bool, list[str]]:
    """One full attempt (both fixtures). Returns (passed, failure_messages).

    Transport/contract problems raise E2EError (not retryable here — they
    propagate up). Only the *assertions* about the LLM's choice are graded, so
    flaky-LLM tolerance is handled by the caller's retry loop.
    """
    child = run_fixture(
        pipeline=pipeline,
        api_url=api_url,
        pool_id=pool_id,
        fixtures_dir=fixtures_dir,
        fixture=CHILD_FIXTURE,
    )
    adult = run_fixture(
        pipeline=pipeline,
        api_url=api_url,
        pool_id=pool_id,
        fixtures_dir=fixtures_dir,
        fixture=ADULT_FIXTURE,
    )

    _print_run("CHILD", child)
    _print_run("ADULT", adult)

    failures: list[str] = []
    # The child face must steer selection to the child-only content (#4).
    if child.chosen_id != CHILD_CONTENT_ID:
        failures.append(
            f"child fixture selected id={child.chosen_id} "
            f"({child.chosen_name!r}); expected id={CHILD_CONTENT_ID} "
            f"({CHILD_CONTENT_NAME!r})."
        )
    # The adult face must NOT land on the child-only content.
    if adult.chosen_id == CHILD_CONTENT_ID:
        failures.append(
            f"adult fixture selected the child-only id={CHILD_CONTENT_ID} "
            f"({CHILD_CONTENT_NAME!r}); demographics did not steer away from it."
        )
    return (not failures), failures


def run_e2e(
    *,
    api_url: str = DEFAULT_API_URL,
    pool_id: int = DEFAULT_POOL_ID,
    fixtures_dir: Path | None = None,
    retries: int = 2,
) -> None:
    """Run the E2E proof, retrying the LLM-graded assertions up to ``retries``.

    Raises AssertionError on a clean assertion failure, E2EError on a transport
    or contract failure. Returns None on success.
    """
    fdir = fixtures_dir or DEFAULT_FIXTURES_DIR
    pipeline = make_pipeline()
    last_failures: list[str] = []
    attempts = max(1, retries + 1)
    for i in range(1, attempts + 1):
        print(f"\n=== attempt {i}/{attempts} ===")
        passed, last_failures = _attempt(
            pipeline=pipeline,
            api_url=api_url,
            pool_id=pool_id,
            fixtures_dir=fdir,
        )
        if passed:
            print("\nPASS: demographics -> target_group -> content verified.")
            return
        print("\n  (assertion(s) failed this attempt:)", file=sys.stderr)
        for f in last_failures:
            print(f"    - {f}", file=sys.stderr)

    raise AssertionError(
        "E2E audience-steering FAILED after "
        f"{attempts} attempt(s):\n  - " + "\n  - ".join(last_failures)
    )


# --------------------------------------------------------------------------- #
# pytest entry point (collected only when run under pytest; self-skips if the
# API is not reachable so a plain `pytest` run does not hard-fail).
# --------------------------------------------------------------------------- #
def test_e2e_audience() -> None:  # pragma: no cover - exercised live, not in unit CI
    import os

    try:
        import pytest
    except ImportError:  # not under pytest; nothing to do
        return

    api_url = os.environ.get("E2E_API_URL", DEFAULT_API_URL)

    # Skip (don't fail) when the API isn't up — this file is primarily a
    # manual/live gate, not a hermetic unit test.
    try:
        requests.get(f"{api_url.rstrip('/')}/pools/{DEFAULT_POOL_ID}", timeout=5)
    except requests.RequestException:
        pytest.skip(f"API not reachable at {api_url}; skipping live E2E")

    # Inference deps/models may be absent off-board — skip rather than error.
    try:
        make_pipeline()
    except E2EError as e:
        pytest.skip(str(e))

    run_e2e(api_url=api_url)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--api-url", default=DEFAULT_API_URL,
                   help=f"CMS/FastAPI base URL (default: {DEFAULT_API_URL})")
    p.add_argument("--pool-id", type=int, default=DEFAULT_POOL_ID,
                   help=f"pool id to select from (default: {DEFAULT_POOL_ID})")
    p.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES_DIR,
                   help=f"fixtures dir (default: {DEFAULT_FIXTURES_DIR})")
    p.add_argument("--retries", type=int, default=2,
                   help="extra retries for the LLM-graded assertions (default: 2)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print("E2E audience -> content steering proof")
    print(f"  api     : {args.api_url}")
    print(f"  pool    : {args.pool_id}")
    print(f"  fixtures: {args.fixtures}")
    try:
        run_e2e(
            api_url=args.api_url,
            pool_id=args.pool_id,
            fixtures_dir=args.fixtures,
            retries=args.retries,
        )
    except AssertionError as e:
        print(f"\nFAIL: {e}", file=sys.stderr)
        return 1
    except E2EError as e:
        print(f"\nERROR (transport/contract): {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
