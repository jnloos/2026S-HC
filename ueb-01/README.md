# 🖥️ DigSig Prototype

Research prototype for the *Heterogeneous Computing* course (2026S, Übung 01)
that compares **three architectural variants of context-aware Digital Signage**
— **edge-only**, **hybrid**, and **cloud-only** — on an Arduino **UNO Q** board
driven by a FastAPI CMS.

A signage display picks **which HTML screen to show** based on **context**
(who is in front of the camera + optional signals like weather/time). The same
decision is implemented three ways so the variants can be compared on selection
quality, latency, bandwidth, privacy, and cost.

| Variant | Where the decision happens | Endpoint used |
|---------|----------------------------|---------------|
| **V1 — edge-only** | Board picks locally via an **on-device LLM**; CMS only serves HTML | `GET /pools/{id}` |
| **V2 — hybrid** | Board does vision locally, sends an abstract context descriptor; **Claude** picks | `POST /pools/{id}/choose-by-context` |
| **V3 — cloud-only** | Board sends the **raw camera frame**; Claude does vision **and** selection | `POST /pools/{id}/choose-by-img` |

---

## 📄 Report

The written project report is the course deliverable:

- **Report (PDF):** [`report/essay/report.pdf`](report/essay/report.pdf) — source: [`report.tex`](report/essay/report.tex)
- **Assignment / task sheet:** [`report/task/2026S_Ubung_HC01.pdf`](report/task/2026S_Ubung_HC01.pdf)
- **Diagrams:** [`report/diagrams/`](report/diagrams/) (Mermaid `.mmd` + rendered `.png`)
- **Working notes** (raw material, chronological issue/feature write-ups): [`report/notes/`](report/notes/)

---

## Repository layout

| Folder | What it is |
|--------|------------|
| [`arduino/`](arduino/) | The **UNO Q App** (App Lab): `app.yaml`, `python/` pipeline, `sketch/`, `assets/` (board UI), and the vendored `bricks/personal_llm/`. **Only this folder is synced to the board.** |
| [`api/`](api/) | The **FastAPI CMS** — pools of HTML content + the three variant endpoints. Own venv; see [`api/README.md`](api/README.md). |
| [`cli/`](cli/) | Bash helpers for the board: `dev.sh`, `configure.sh`, `rsync.sh`, `control.sh`, `verify-pipelines.sh`. |
| [`detection/`](detection/) | Self-contained **model-training** subproject for the on-device audience classifier (FairFace → MobileNetV3 → ONNX). See [`detection/README.md`](detection/README.md). |
| [`web/`](web/) | Static assets for the **API's** opt-in debug UI (served under `/debug`). |
| [`report/`](report/) | The report, task sheet, diagrams, and notes (see above). |
| [`.claude/knowledge/`](.claude/knowledge/) | UNO Q / App Lab knowledge base — read before changing board code. |

---

## How to use the app

The system has two halves: the **CMS** (`api/`, runs on your laptop) and the
**board App** (`arduino/`, runs on the UNO Q). For a normal demo you run both.

### 1. Start the CMS (FastAPI)

```bash
cd api
python -m venv .venv && source .venv/bin/activate   # fish: source .venv/bin/activate.fish
pip install -e ".[dev]"        # installs deps + the `digsig` CLI
digsig db upgrade              # create the DB schema (Alembic — not auto-created)

cp env.xmpl .env               # then set ANTHROPIC_API_KEY for variants 2 & 3
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

- Health: <http://localhost:8000/health> · API docs: <http://localhost:8000/docs>
- `ANTHROPIC_API_KEY` is **required for V2 and V3** (Claude). V1 needs no key.

### 2. Load demo content

Content lives in **pools**; the LLM picks a screen from the pool by its
**description**. Load the ready-made scenario:

```bash
digsig seed bakery             # demo pool from api/fixtures/bakery/
digsig pool list               # inspect pools
digsig pool show 1             # pool + its contents
```

Manage content yourself with `digsig pool …` / `digsig content …`
(full list in [`api/README.md`](api/README.md)).

### 3. Deploy the App to the board

Board host/paths come from `cli/.env` (copy `cli/env.xmpl`, set `BOARD=` to
your board, e.g. `arduino@uno-q.local`). First run installs an SSH key
(one password prompt), then runs password-free.

The easiest path brings up the **whole stack** — it starts the API, auto-detects
your laptop's LAN IP, points the board's `CMS_URL` at it, syncs `arduino/`, and
restarts the App:

```bash
./cli/dev.sh up                # start everything (idempotent)
./cli/dev.sh status            # API up? detected IP? board App state
./cli/dev.sh logs              # follow the local API log
./cli/dev.sh down              # stop the local API
```

Sync / control the App directly when the API is already up:

```bash
./cli/rsync.sh push            # Laptop -> Board (only arduino/)
./cli/control.sh report        # status + recent logs
./cli/control.sh restart       # restart the App
./cli/control.sh follow        # live log stream
```

The signage display is served by the board's `web_ui` brick on **port 7000**.

### 4. Switch variant / audience / trigger at runtime

These are thin wrappers that write the board's `runtime.env`, re-sync, and
restart:

```bash
./cli/control.sh variant v1|v2|v3      # edge | hybrid | cloud
./cli/control.sh audience static|face  # fixed group | live camera inference
./cli/control.sh trigger timer|person  # what fires a new pick
```

**In-process audience detection** (`face`) runs the ONNX classifier inside the
App (no sidecar) and needs the camera + `onnxruntime`/`opencv-python-headless`
in the App env; if those are missing it logs and falls back to the static
classifier. Enable it with `./cli/control.sh audience face` (forces the camera
on).

> ⚠️ **USB-C port is host *or* device, never both.** The UNO Q's single USB-C
> port drives the camera in **host** mode (the default), which means App Lab
> can't reach the board over USB — use App Lab's **Network** mode, or
> `./cli/control.sh usb-device` to flip it (reboot restores host). See
> [`report/notes/01-usb-host-camera-issue.md`](report/notes/01-usb-host-camera-issue.md).

### 5. Verify the variant pipelines

```bash
./cli/verify-pipelines.sh                 # off-board gates + on-board best-effort
SKIP_ONBOARD=1 ./cli/verify-pipelines.sh  # off-board only (boots a local API, runs V1/V2/V3)
```

---

## Training the audience classifier (optional)

The committed `detection/models/*.onnx` are the real trained artifacts, so you
only retrain to change the model. The subproject has its **own** Python 3.12 /
`uv` env — full instructions in [`detection/README.md`](detection/README.md).
After a retrain, copy the new models into the App
(`arduino/python/audience/models/`) so they ship with it.

---

## Development docs

- [`CLAUDE.md`](CLAUDE.md) — full command reference + non-obvious architecture notes.
- [`.claude/knowledge/`](.claude/knowledge/) — UNO Q / App Lab / Brick model (non-standard; read before touching board code).
- [`api/README.md`](api/README.md) — CMS setup, endpoints, `digsig` CLI, storage layout.
- [`detection/README.md`](detection/README.md) — model training, the frozen ONNX contract, ethics/limitations.
