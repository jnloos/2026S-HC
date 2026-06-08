# 09 — Dev workflow: running & debugging the full stack

How to bring up and debug **all** parts of the prototype at once (FastAPI CMS
on the laptop + Arduino client on the board), and the day-to-day iteration loops.

## 30-second model

Two processes, two machines:

- **CMS (API)** — FastAPI, runs on the **laptop**, binds `0.0.0.0:8000`.
- **Client** — the Arduino App, runs on the **board** (`$BOARD`, e.g. `arduino@uno-q.local`).
  It can only run on-board (needs board-only bricks), and it calls the CMS over
  the LAN at `CMS_URL`.

The board's `CMS_URL` must point at the **laptop's LAN IP** — `localhost` on the
board means the board itself. The laptop IP changes on the LAN, so it is
**auto-detected**; nobody sets it by hand.

## "Dev mode" — one command

```bash
./cli/dev.sh up        # detect laptop IP, start API (0.0.0.0:8000, background),
                       # write runtime.env (CMS_URL=http://<ip>:8000), sync, restart board app
./cli/dev.sh status    # API up? detected IP? board app state
./cli/dev.sh logs      # follow the local API log (.dev/api.log)
./cli/dev.sh restart   # API restart + reconfigure board (e.g. after IP change)
./cli/dev.sh down      # stop the local API
```

`dev.sh up` is the answer to "start up all necessary app parts". It is
idempotent — safe to re-run, e.g. when the laptop's IP changed (Wi-Fi reconnect).
Local API run-state lives in `.dev/` (`api.pid`, `api.log`; gitignored).
Override the port with `API_PORT=9000 ./cli/dev.sh up`.

## Fast reconfigure (no full bring-up)

`cli/configure.sh` only touches the board's runtime settings (writes
`runtime.env`, syncs, restarts) — use it when the API is already running:

```bash
./cli/configure.sh                   # auto-detect IP -> CMS_URL, sync, restart
./cli/configure.sh --ip 192.168.1.9  # pin the CMS host explicitly
./cli/configure.sh TRIGGER_MODE=timer POOL_ID=2   # set any key(s)
./cli/configure.sh --show            # print the active runtime.env
./cli/configure.sh --no-restart      # write + sync only
```

## How runtime config reaches the board

`arduino/python/config.py` loads an optional **`runtime.env`** (KEY=VALUE, in
`arduino/python/`) and overlays it onto `os.environ` **with precedence** — the
file is authoritative. It is dependency-free (no `python-dotenv`) and
**gitignored** (machine-specific; holds the laptop IP). Template:
`arduino/python/runtime.env.xmpl`. Keys: `CMS_URL`, `POOL_ID`, `AUDIENCE_GROUP`,
`TRIGGER_MODE` (`person`|`timer`), `TIMER_INTERVAL_SEC`, `PERSON_DEBOUNCE_SEC`,
`DEBUG`. This exists because `arduino-app-cli` has **no** per-app env-var setter
(only `properties`=default-app and `config get`), so App Lab env isn't scriptable.

Path override: `DIGSIG_ENV_FILE=/abs/path` (used by tests).

## Iteration loops

- **Server change** → edit `api/`, `pytest` (54 tests, Claude mocked), and either
  the running `dev.sh` API picks it up (run with `--reload` manually if you want
  hot reload) or `./cli/dev.sh restart`.
- **Client change** → `./cli/rsync.sh push` → `./cli/control.sh restart` →
  `./cli/control.sh logs --tail 200` (or `follow`). The client cannot run off the
  board. `configure.sh`/`dev.sh` already push+restart for you.

## Seeing it (browser)

Both UIs are reachable from the laptop and drivable via the **Playwright MCP**
(navigate / screenshot / console):

- **API debug UI**: `http://<laptop-ip>:8000/debug` (needs `DEBUG_UI_ENABLED=true`
  in `api/.env`; add `?token=…` if `DEBUG_TOKEN` set).
- **Board signage + debug UI**: `http://<board-host>:7000` (the
  `arduino:web_ui` brick serving `arduino/assets/`; `DEBUG=true` shows the
  event stream + camera PiP).

## Access prerequisites (all already in place)

- Passwordless SSH to the board (`cli/_common.sh` bootstraps the key).
- `api/.venv` with deps + the `digsig` CLI; `api/.env` with `ANTHROPIC_API_KEY`
  (V2/V3) and `DEBUG_UI_ENABLED=true`.
- `.claude/settings.local.json` allowlists the dev commands so they run without
  per-call permission prompts.
