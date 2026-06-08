# Arduino App Lab & Apps

**Arduino App Lab** is the unified IDE/environment for building **Apps** for the
dual-brain boards (UNO Q). The model is "compose by stacking pre-built
components (Bricks)" rather than writing everything from scratch. It supports
both Python (Linux) and Arduino sketch (C++) development in one App.

## What is an App?

An App is a package combining a Linux-side and an MCU-side program. **Only one
App runs on the board at a time.**

### Core files (by convention — do not rename the folders)
```
my-app/
├── app.yaml            # App config + declared Bricks (managed by App Lab/tooling)
├── python/
│   └── main.py         # Linux-side Python entry point
├── sketch/
│   ├── sketch.ino      # MCU-side Arduino/C++ sketch
│   └── sketch.yaml     # sketch build config (platform: arduino:zephyr)
└── assets/             # OPTIONAL — web UI files etc. (only if a Brick needs it)
```
- `python/` and `sketch/` folders and the `main.py` / `sketch.ino` entry points
  are **required by convention**. Renaming/removing breaks the App.
- `assets/` is optional; present when using the Web UI Brick (serves its contents).

### `app.yaml` shape
```yaml
name: Blink LED
icon: 🔴
description: This example shows how to make the LED blink alternately.
bricks:                       # optional; lists Bricks used by the App
  - arduino:web_ui
  - arduino:object_detection
  - arduino:vlm:              # some Bricks take config (e.g. a model)
      model: genie:qwen2_5_vl_7b_instruct
```

### `sketch.yaml` shape
```yaml
profiles:
  default:
    platforms:
      - platform: arduino:zephyr
default_profile: default
```

## `main.py` skeleton

```python
from arduino.app_utils import App, Bridge   # core utilities
from arduino.app_bricks.web_ui import WebUI  # any Bricks you declared

# ... set up bricks, register callbacks, provide Bridge functions ...

App.run()   # MUST be the very last line
```

### `App.run()`
- Required in **every** App; place at the **very bottom** of `main.py` (anything
  after it is ignored).
- It launches all included Bricks and keeps the App alive (so Bridge-provided
  methods stay callable).
- Optional user loop: `App.run(user_loop=loop)` repeatedly calls your `loop`
  function.

```python
import time
led_state = False
def loop():
    global led_state
    time.sleep(1)
    led_state = not led_state
    Bridge.call("set_led_state", led_state)

App.run(user_loop=loop)
```

Other `app_utils` exports seen in examples: `App`, `Bridge`, `Logger`,
`FrameDesigner`. (`from arduino.app_utils import *` is common in examples.)

## App lifecycle (what happens on Launch)
1. `sketch.ino` is **compiled on the board** (on the Linux side) and uploaded to
   the MCU.
2. `main.py` launches on the Linux system.
Both are monitored via the **Console** tab (start-up logs, **main** = Python
logs from `print()`, **Sketch** = serial output from `Monitor.print()`).

```cpp
Monitor.print("Data: ");
Monitor.println(data);   // shows in the Sketch console tab
```

## Web UI / accessing a running App
- Many Apps host a web interface via the **Web UI Brick** (serves `assets/`).
- Local: `http://localhost:7000`
- From another device on the same network: `http://<board-hostname>.local:7000`

## Creating apps in App Lab
- **My Apps → Create New App** → wizard gives an empty template.
- Built-in **Examples** are read-only; use **"Copy and Edit App"** to duplicate
  one into an editable project. Edit files via the File Manager.

## Troubleshooting

### Build fails: `no colon in first item of depfile`
This is `arduino-cli`'s dependency-file parser choking on a **stale/corrupt
`.d` build artifact**, not a code problem. It aborts at the up-to-date check —
right after the `The library ... has been added` lines, before any real
compile output.

**Cause:** the sketch is compiled **on the board**, and the per-app build
cache lives in `.cache/` inside the app dir on the board. `.cache/` is
gitignored and `rsync.sh push` runs without `--delete`, so a cache from a
previous build (e.g. before bricks/libraries were added) rots there. When the
library set changes, the cached `.d` files no longer match → parse error.

**Fix:** wipe the stale cache and rebuild clean. The cache only exists on the
board, so:
```sh
# mirror local → board and delete board-only files (incl. .cache/).
# DRY-RUN FIRST — --delete removes anything on the board not present locally.
./rsync.sh push --delete --dry-run   # confirm only .cache/... is deleted
./rsync.sh push --delete
```
If the in-app clean isn't enough, also clear arduino-cli's global cache on the
board (outside the app dir, so rsync won't touch it):
`ssh "$BOARD" 'rm -rf ~/.cache/arduino/sketches'`.
Then re-launch from App Lab. (Confirmed fix 2026-05-27.)
