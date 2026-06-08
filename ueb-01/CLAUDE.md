# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# ARDU-DigSig-Prototype

Research prototype comparing **three Digital-Signage architectural variants**
(edge-only / hybrid / cloud-only). Not a generic UNO Q demo — see
`.claude/knowledge/08-project-goal.md` for the variant overview before
designing changes.

Monorepo top-level folders:

- **`arduino/`** — Arduino **UNO Q** App (App Lab; dual-brain board: Linux MPU +
  STM32 MCU, Brick-based model). Only this folder is synced to the board via
  `cli/rsync.sh`. Python lives in `arduino/python/`; the App's own browser
  frontend (served by the `arduino:web_ui` brick) is in `arduino/assets/`.
- **`cli/`** — Bash helper scripts for the board (`rsync.sh` sync, `control.sh`
  remote app control, `dev.sh`/`configure.sh` full-stack + runtime config).
  Config (board host, app id, paths) is read from `cli/.env` (copy
  `cli/env.xmpl`); scripts self-bootstrap password-less SSH on first run.
- **`api/`** — **FastAPI** Python service (the CMS). Independent venv; not synced
  to the board. The three variant endpoints live here.
- **`detection/`** — **Self-contained model-training subproject** for the
  on-device audience classifier. Its own Python **3.12** env (via `uv`, separate
  from `api/`). Trains the FairFace age/gender classifier (`scripts/`) and exports
  to `detection/models/` (the only non-gitignored artifacts). The **inference**
  itself runs **in-process inside the App** — see `arduino/python/audience/inference.py`
  — not as a sidecar. See `detection/README.md`.
- **`web/`** — Static assets for the **API's** opt-in debug UI; served by
  FastAPI under `/debug` and `/debug/static` when `DEBUG_UI_ENABLED=true`. Do
  not confuse with `arduino/assets/`, which is the Arduino App's own UI.
- **`report/`** — Project documentation: `notes/` (chronological feature/issue
  write-ups, e.g. `06-audience-detection.md`) and `diagrams/` (Mermaid + PNG).

Two separate web UIs exist — `arduino/assets/` is the signage display + live
debug window served on the board (port 7000); `web/` is the FastAPI service's
debug UI. They are unrelated codebases.

## ⚠️ Before working on this project

The UNO Q + App Lab model (Apps, Bricks, Bridge) is non-standard and is
documented in `.claude/knowledge/`. Read the index first:

- `README.md` — index + 30-second mental model
- `01-board-uno-q.md` — hardware, pinout, voltages
- `02-app-lab-and-apps.md` — App structure, files, lifecycle
- `03-bridge.md` — MPU↔MCU RPC
- `04-bricks.md` — Brick catalog + API patterns
- `05-ai-models.md` — on-device AI
- `06-setup-and-modes.md` — USB/Network/SBC modes
- `07-api-architecture.md` — chosen architecture for `api/`; new features must follow this pattern
- `08-project-goal.md` — the three variants this prototype compares
- `09-dev-workflow.md` — the `cli/dev.sh` full-stack dev loop + auto-IP wiring

Official docs: https://docs.arduino.cc/software/app-lab/ ·
examples: https://github.com/arduino/app-bricks-examples

## Common commands

### Dev mode — run the whole stack (`cli/dev.sh`)
Brings up **all parts** for development: starts the API on the laptop
(`0.0.0.0:8000`, background), auto-detects the laptop's LAN IP, points the
board's `CMS_URL` at it, syncs, and restarts the board app. The laptop IP is
**never set by hand** — it's detected each run. See `09-dev-workflow.md`.
```bash
./cli/dev.sh up        # start everything (idempotent — re-run after an IP change)
./cli/dev.sh status    # API up? detected IP? board app state
./cli/dev.sh logs      # follow the local API log (.dev/api.log)
./cli/dev.sh restart   # API restart + reconfigure board
./cli/dev.sh down      # stop the local API
```
Fast board-only reconfigure (API already running):
```bash
./cli/configure.sh                 # auto-IP -> CMS_URL, sync, restart
./cli/configure.sh TRIGGER_MODE=timer POOL_ID=2   # set any runtime key(s)
./cli/configure.sh --show          # print the active runtime.env
```

Board host, app id and paths come from `cli/.env` (copy `cli/env.xmpl`).
`BOARD` is **required** (no built-in default — it's machine-specific); the
scripts fail with a clear message if it's unset. Other defaults live in
`cli/_common.sh`. On first run the scripts generate an SSH key if needed and
install it on the board (`ssh-copy-id`, one-time password prompt), then run
password-free.

### Sync the Arduino App to the board
```bash
./cli/rsync.sh push            # Laptop -> Board (only arduino/, no --delete)
./cli/rsync.sh push --dry-run  # preview
./cli/rsync.sh pull            # Board -> Laptop
```

### Control the App on the board
`cli/control.sh` is an SSH wrapper around `arduino-app-cli` for the deployed
App (`user:digsig-prototype`).
```bash
./cli/control.sh report          # status + recent logs (default)
./cli/control.sh start | stop | restart
./cli/control.sh logs [flags]    # extra flags passed through, e.g. --tail 200
./cli/control.sh follow          # live log stream (Ctrl-C to stop)
./cli/control.sh shell           # SSH shell in the App dir on the board
```
Pipeline settings (thin wrappers over `configure.sh` — write `runtime.env`, sync,
restart; `face`/`person`/`cloud` also force `ENABLE_CAMERA=true`):
```bash
./cli/control.sh variant v1|v2|v3        # SELECTOR_MODE = edge | hybrid | cloud
./cli/control.sh audience static|face    # AUDIENCE_MODE
./cli/control.sh trigger timer|person    # TRIGGER_MODE
./cli/control.sh config KEY=VALUE ...    # set any runtime key(s); --show to print
```
USB-C port role (the board's single port is OTG/dual-role — `host` for the
camera vs. `device` for App Lab over USB; see "USB-C port role" below):
```bash
./cli/control.sh usb-status      # current role + uno-q-usb-host.service state + lsusb
./cli/control.sh usb-host        # camera/peripheral mode (default; starts the service)
./cli/control.sh usb-device      # USB-gadget mode for App Lab over USB (alias: usb-client)
```

### Enable in-process audience detection
The audience classifier runs **in-process** in the App (no sidecar/container). The
ONNX models ship with the App under `arduino/python/audience/models/` and sync
with `rsync.sh`. To turn it on (needs the camera):
```bash
./cli/configure.sh AUDIENCE_MODE=face ENABLE_CAMERA=true && ./cli/control.sh restart
```
It needs `onnxruntime` + `opencv-python-headless` in the App's Python env
(`arduino/python/requirements.txt`). If those wheels are absent the App logs and
**falls back to the static audience classifier** rather than crashing — see
`_make_audience_pipeline()` in `arduino/python/main.py`.

### Verify all three variant pipelines (`cli/verify-pipelines.sh`)
```bash
./cli/verify-pipelines.sh            # off-board (gates exit) + on-board best-effort
SKIP_ONBOARD=1 ./cli/verify-pipelines.sh   # off-board only — boots local API, runs V1/V2/V3 (+ face->V2)
```
The `face->V2` row needs cv2 + onnxruntime in the runner's Python; set
`VERIFY_PYTHON=detection/.venv/bin/python` to exercise it, else it SKIPs.

### Training the audience classifier (`detection/`)
Separate Python 3.12 / `uv` project. Heavy (FairFace ~4 GB cached, ~13 epochs CPU);
the committed `detection/models/*.onnx` are the real trained artifacts, so a
retrain is only needed to change the model. **After a retrain, copy the new
models into the App** (`cp detection/models/{labels.json,*.onnx} arduino/python/audience/models/`).
```bash
cd detection
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python torch torchvision --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python -r requirements.txt
bash scripts/run_all.sh --subset 8000   # fetch_models->download_data->prepare->train->export_onnx->make_fixtures->sanity_infer
```
Inference tests live with the App (`cd arduino/python && pytest tests/test_inference.py`);
they skip when the ONNX models or cv2/onnxruntime aren't present.

### API development (`api/`)
```bash
cd api
source .venv/bin/activate          # fish: source .venv/bin/activate.fish
pip install -e ".[dev]"            # installs deps + the `digsig` CLI
digsig db upgrade                  # apply Alembic migrations (schema is NOT auto-created)
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
pytest                             # all tests (Claude API is mocked, isolated tmp STORAGE_DIR)
pytest tests/test_routes.py::test_x # single test
```
Copy `api/env.xmpl` → `api/.env` and set `ANTHROPIC_API_KEY=...` for variants
2 & 3. Optional: `CLAUDE_MODEL` (default `claude-haiku-4-5`), `DEBUG_UI_ENABLED`,
`DEBUG_TOKEN`.

### Content management via CLI
Pools and contents are managed exclusively through the `digsig` CLI — HTML
snippets are stored on disk (`storage/pools/<pool_id>/<content_id>.html`),
only metadata in the DB. See `api/README.md` for the full command list.
`digsig seed bakery` loads the ready-made demo scenario from
`api/fixtures/bakery/`. Note: a content's **description** (not its HTML) is the
primary signal the LLM uses to pick — fixtures spell out audience/weather/
time-of-day cues explicitly, and V3's image is the camera frame, not the
snippet.

## Architecture notes (non-obvious)

- **USB-C port role is a hard either/or.** The UNO Q has a *single* USB-C port
  that is OTG/dual-role: it's either **host** (drives the camera/peripherals) or
  **device** (presents the board as a USB gadget to a laptop, which App Lab's USB
  mode needs) — never both. When powered via VIN/5V the controller boots in
  device mode with VBUS off, so the camera needs the port forced to `host`. That
  is made persistent by a board-side systemd unit **`uno-q-usb-host.service`**
  (writes `host` to `/sys/kernel/debug/usb/4e00000.usb/mode` at boot;
  `report/notes/01-usb-host-camera-issue.md`). Consequence: while host mode is on
  (the default), **App Lab cannot reach the board over the USB cable** — use App
  Lab's **Network** mode, or flip the port with `./cli/control.sh usb-device`
  first (reboot restores host). `./cli/control.sh usb-status` shows the live
  state. The clean hardware escape is powering the board via the `5VIN` pin.
- **Three runtime endpoints**, one per variant:
  - V1 edge-only:  `GET  /pools/{id}` (Arduino picks locally via on-device LLM)
  - V2 hybrid:     `POST /pools/{id}/choose-by-context` (open JSON body; any keys flow into the Claude prompt)
  - V3 cloud-only: `POST /pools/{id}/choose-by-img` (multipart image + optional `context` JSON form field)
- **Arduino app is a strategy-slot pipeline.** `arduino/python/main.py` is the
  composition root: it wires one implementation from each of `triggers/`
  (timer | person), `audience/`, `pickers/` (edge | hybrid | cloud), `sinks/`,
  plus `cms/` (talks to the FastAPI service). Variants are selected by
  swapping the picker — no other module knows about specific variants. Add new
  variants/features by writing new strategy implementations and wiring them in
  `main.py`.
- **`pipeline/` is the per-cycle orchestrator**, not a strategy slot.
  A trigger calls `Pipeline.run_once(ctx)`, which runs
  `classifier → selector → sink` in order, merging audience info into the
  context between stages. It **never raises** — a failure in any stage is
  caught and surfaced via `sink.publish_error()` so the display degrades
  instead of going silent, and (in debug) emits per-stage `stage`/`run_done`
  timing events so the debug window can show where time goes
  (inference-dominated on edge, network on cloud).
- **All three variants are wired; pick one with `SELECTOR_MODE`.** `main.py`
  constructs `EdgeSelector` (`edge`/V1), `HybridSelector` (`hybrid`/V2) or
  `CloudSelector` (`cloud`/V3) from `SELECTOR_MODE` (default `edge`). Each
  selector is fully implemented: edge picks via the on-device LLM, hybrid POSTs
  the context to `/choose-by-context`, cloud POSTs the camera frame to
  `/choose-by-img`. Switching variant is a one-runtime-key change
  (`./cli/control.sh variant v1|v2|v3`). Cloud (V3) needs a camera frame, so it
  raises `SelectorError` if `ENABLE_CAMERA` is off — the `variant` helper forces
  the camera on for V3.
- **Arduino app is configured by env vars**, read once at import in
  `arduino/python/config.py` (`Settings`): `CMS_URL`, `POOL_ID`,
  `SELECTOR_MODE` (`edge` | `hybrid` | `cloud` → V1/V2/V3, default `edge`),
  `AUDIENCE_MODE` (`static` | `face`; `face` requires the camera),
  `AUDIENCE_GROUP`, `TRIGGER_MODE` (`person` | `timer`), `TIMER_INTERVAL_SEC`,
  `PERSON_DEBOUNCE_SEC`, `LLM_TIMEOUT_SEC` (default 240 — the on-device LLM is
  slow, ~1-2 min/pick), `ENABLE_CAMERA` (default on; set false to free CPU for
  the LLM, which forces the person trigger to fall back to timer), `DEBUG`.
  Defaults target on-board dev (`DEBUG` and `person` trigger are **on** by
  default). `app.yaml` declares the bricks
  (`arduino:web_ui`, `arduino:video_object_detection`, `personal:llm`) and
  exposes port 7000.
- **`runtime.env` overrides the board config without App Lab.** `config.py`
  overlays an optional `arduino/python/runtime.env` (KEY=VALUE, gitignored,
  template `runtime.env.xmpl`) onto `os.environ` **with precedence** — it's the
  scriptable way to set `CMS_URL` etc., since `arduino-app-cli` has no per-app
  env setter. Managed by `cli/configure.sh` / `cli/dev.sh` (auto-detected laptop
  IP), so the board's `CMS_URL` is never hand-edited. `DIGSIG_ENV_FILE` overrides
  the path (tests use this).
- **Arduino debug channel mirrors the API's.** When `DEBUG` is on,
  `arduino/python/debug/` adds a structured event bus (`events.py`: `DebugBus`
  emits `debug_event` WebUI messages keyed by `kind`; `BusLogHandler` forwards
  WARNING+ logs; `HealthReporter` re-broadcasts CMS/brick readiness) plus
  `streamer.py` (`DebugStreamer` pushes the live camera frame for the debug
  PiP). All of it is no-op when `DEBUG` is off — pass `DebugBus` unconditionally
  at call sites. The frontend (`arduino/assets/`) consumes these over
  socket.io; the normal signage display uses `content_update` messages from
  `WebUISink`.
- **`personal:llm` is a vendored custom brick** at `arduino/bricks/personal_llm/`
  — the stock `arduino:llm` brick couldn't be installed via App Lab, so its
  source was copied in. Referenced by id `personal:llm` from `arduino/app.yaml`
  and imported as `from personal_llm import LargeLanguageModel`. Provides the
  on-device LLM that V1's `EdgeSelector` uses.
- **Thin web/CLI layers over shared `services/` core.** Both `app/api/` and
  `app/cli/` are intentionally thin wrappers — business logic lives in
  `app/services/` and must be shared. Follow this pattern for new features
  (see `07-api-architecture.md`).
- **Claude prompts are Jinja2 templates** in `app/templates/*.j2`, not Python
  strings — tune prompts without touching code.
- **Claude responses are parsed as JSON** with a validation pass that rejects
  content ids the model invents.
- **Schema is managed by Alembic**, not auto-created on app startup. Always
  run `digsig db upgrade` after pulling new migrations.
- **Debug UI is opt-in.** When `DEBUG_UI_ENABLED=true`, `app/api/main.py` adds
  `DebugMiddleware`, mounts the `app/debug/` router at `/debug` (index + SSE
  stream + `/recent` backfill), and serves `web/static/` at `/debug/static`.
  Auth is open if `DEBUG_TOKEN` is empty; otherwise `?token=…` or
  `Authorization: Bearer …` is required.
