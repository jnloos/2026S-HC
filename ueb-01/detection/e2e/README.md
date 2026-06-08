# Audience detection — end-to-end verification

Two checks prove the audience classifier actually steers signage content
by demographics:

1. **Image-injected E2E** (`test_e2e_audience.py`) — autonomous, no camera. Feeds
   fixed JPEG fixtures through the real `AudiencePipeline.classify` →
   `choose-by-context` chain (inference runs **in-process**, no sidecar).
2. **Live-camera check** — a 5-minute manual smoke test in front of the screen.
   This is the only non-autonomous step.

The full pipeline being verified:

```
camera/JPEG ─► AudiencePipeline.classify()  (in-process face inference ─► audience dict)
            ─► API POST /pools/{id}/choose-by-context  (V2 hybrid, Claude)
            ─► chosen content id ─► screen
```

The audience dict is sent as the `"audience"` key of the open-shaped V2 context
envelope — exactly what the board builds in
`arduino/python/pipeline/context.py`.

---

## 1. Image-injected E2E (`test_e2e_audience.py`)

Proves **demographics → target_group → content WITHOUT a camera or a real
child**: a `child.jpg` fixture must select bakery content **#4
"Kinder-Naschstation"** (its description: *"NUR anzeigen, wenn Kinder …
erkannt werden"*), and `young-adult_female.jpg` must NOT.

### Preconditions

* **API up, Claude key, bakery seeded:**
  ```bash
  cd api
  cp .env.xmpl .env            # then set ANTHROPIC_API_KEY=...
  source .venv/bin/activate    # fish: source .venv/bin/activate.fish
  digsig db upgrade
  digsig seed bakery           # creates pool #1, contents #1..#6
  ```
  Bring up the stack (API on `0.0.0.0:8000`):
  ```bash
  ./cli/dev.sh up
  ```
* **Inference deps + models** available to the Python running the script:
  `cv2` + `onnxruntime`, and the ONNX models (bundled at
  `arduino/python/audience/models/`, or set `AUDIENCE_MODEL_DIR`). The
  `detection/.venv` already has the wheels.
* **Fixtures** under `arduino/python/tests/fixtures/`: `child.jpg`,
  `young-adult_female.jpg` (produced by `detection/scripts/make_fixtures.py`).

### Run

```bash
# Use a Python that has requests + cv2 + onnxruntime (e.g. detection/.venv):
detection/.venv/bin/python detection/e2e/test_e2e_audience.py

# Against a remote API, with explicit options:
detection/.venv/bin/python detection/e2e/test_e2e_audience.py \
  --api-url   http://localhost:8000 \
  --pool-id 1 \
  --fixtures arduino/python/tests/fixtures \
  --retries 2
```

* Prints each fixture's `target_group`, the chosen `chosen_id`/name, and the
  LLM `reasoning`.
* Exit `0` = pass, `1` = assertion failure (LLM chose wrong), `2` = transport/
  contract error (the API is down or replied unexpectedly).
* `--retries` re-runs the LLM-graded assertions to absorb occasional Claude
  flakiness (transport errors are not retried — they surface immediately).

It is also pytest-collectable (`test_e2e_audience`); under `pytest` it **skips**
(does not fail) when the API isn't reachable or the inference deps/models are
missing. Override the API URL with `E2E_API_URL`.

### API contract (verified, not guessed)

* Endpoint: `POST /pools/{pool_id}/choose-by-context`
  (`api/app/api/routers/pools.py`).
* Body: a **raw JSON object** (`RootModel`) — any keys flow into the Claude
  prompt; sent here as `{"audience": <classify dict>}`.
* Response field for the picked content id: **`chosen_id`**
  (alongside `name`, `description`, `html`, `reasoning`).

---

## 2. Live-camera check (manual, ~5 min — the only non-autonomous step)

With the stack up and the app wired to use the in-process classifier:

```bash
# Wire the app to the camera + in-process inference, then restart it:
./cli/configure.sh AUDIENCE_MODE=face ENABLE_CAMERA=true
./cli/control.sh restart

# USB-C must be in HOST mode for the camera (see cli/control.sh):
./cli/control.sh usb-host
```

Then:

1. **Stand in front of the camera** (or hold up a printed face photo — an
   adult and, ideally, a child/cartoon face). One person is enough.
2. **Watch the classification** via the board debug window
   (`http://<board-host>:7000`) — the `face` events show `target_group`, and the
   live camera PiP confirms the frame. Or follow the app log:
   `./cli/control.sh follow`.
3. **Confirm `target_group` is sensible** for who is in front (e.g. an adult →
   not `families_with_children`; a child/family face → `families_with_children`).
4. **Confirm the content changes** to match: a child in frame should bring up
   **"Kinder-Naschstation"** on the signage display; an adult should not.

### Quick triage if content doesn't change

| Symptom | Check |
| --- | --- |
| Log says "falling back to static audience" | inference deps/models missing → install `onnxruntime opencv-python-headless` on the board; confirm models synced under `arduino/python/audience/models/` |
| No `face` classify events in the log | app not wired → `AUDIENCE_MODE=face ENABLE_CAMERA=true` + `control.sh restart` |
| `people_count: 0` always | camera not in HOST mode → `./cli/control.sh usb-host`; check lighting/framing |
| `target_group` ok but content stale | API/Claude path → check `./cli/dev.sh logs` and `ANTHROPIC_API_KEY` |
