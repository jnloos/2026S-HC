# Arduino UNO Q + App Lab — Knowledge Base

> **READ THIS BEFORE WORKING ON THIS PROJECT.** The Arduino UNO Q is a new
> "dual-brain" board with its own App Lab toolchain and a Brick-based API model
> that differs significantly from classic Arduino development. This folder is the
> distilled reference so we don't re-derive it each session.

Source of truth: Arduino official docs (`docs.arduino.cc/software/app-lab/`,
`docs.arduino.cc/hardware/uno-q/`) and the official examples repo
[`arduino/app-bricks-examples`](https://github.com/arduino/app-bricks-examples)
(the `learn-docs/` folder + working `examples/`). Captured 2026-05-27 against
App Lab ~0.7.

## Files

| File | What's in it |
|------|--------------|
| [01-board-uno-q.md](01-board-uno-q.md) | Hardware: MPU + MCU, memory, pinout, voltages, connectors |
| [02-app-lab-and-apps.md](02-app-lab-and-apps.md) | App Lab IDE, App structure, files, lifecycle, logs, Web UI |
| [03-bridge.md](03-bridge.md) | Bridge RPC — how Python (MPU) ↔ sketch (MCU) talk |
| [04-bricks.md](04-bricks.md) | What Bricks are, how to add/import them, full catalog + API patterns |
| [05-ai-models.md](05-ai-models.md) | On-device AI models, how they bind to Bricks |
| [06-setup-and-modes.md](06-setup-and-modes.md) | USB/Network/SBC modes, board setup, networking |
| [07-api-architecture.md](07-api-architecture.md) | FastAPI service (`api/`): layering, CLI, SQLite, storage, file distribution |
| [08-project-goal.md](08-project-goal.md) | **What this prototype is for**: Digital Signage with 3 variants (edge-only / hybrid / cloud-only Mistral) |
| [09-dev-workflow.md](09-dev-workflow.md) | **Running & debugging the full stack**: `cli/dev.sh up` ("dev mode"), auto-IP `CMS_URL`, `runtime.env`, iteration loops, both web UIs |

## The 30-second mental model

- **Two processors, one board.** A Linux **MPU** (Qualcomm QRB2210, quad A53,
  runs Debian + Python) and an **MCU** (STM32U585, Cortex-M33, classic Arduino).
- **You write Apps**, not just sketches. An App = `python/main.py` (Linux) +
  `sketch/sketch.ino` (MCU) + `app.yaml`. Only one App runs at a time.
- **Bricks** are pre-built Python building blocks (AI vision, audio, LLM, web UI,
  storage, cloud…) you declare in `app.yaml` and `import` in `main.py`.
- **Bridge** connects the two sides via RPC (`provide` / `call`).
- **`App.run()`** at the very bottom of `main.py` launches everything.
