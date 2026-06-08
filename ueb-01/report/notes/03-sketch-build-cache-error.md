# Issue: Korrupter Sketch-Build-Cache beim App-Restart (offen)

**Status:** offen — beim App-Restart am 2026-06-04 aufgetreten, noch nicht behoben.

## Symptom
Beim `./cli/control.sh restart` schlägt der Sketch-Build auf dem Board fehl:
```
arm-zephyr-eabi-ar: .../digsig-prototype/.cache/sketch/core/core.a:
  error reading WMath.cpp.o: file truncated
[ERROR] Exit Status 1
```

## Vermutete Ursache
Eine **truncated** (abgeschnittene) Objektdatei im Sketch-Build-Cache
(`~/ArduinoApps/digsig-prototype/.cache/sketch/`). Wahrscheinlich durch einen
**Reboot, der einen laufenden Build unterbrochen hat** (oder abgebrochenes
Schreiben in den Cache). Betrifft den MCU-/Sketch-Teil, nicht den Python-Teil.
Unabhängig vom Kamera-Problem (Issue 01).

## Geplanter Fix (noch auszuführen)
Build-Cache leeren und neu bauen lassen:
```bash
ssh "$BOARD" 'rm -rf ~/ArduinoApps/digsig-prototype/.cache/sketch'
./cli/control.sh restart
./cli/control.sh logs --tail 50   # auf erfolgreichen Build + Kamera-Init prüfen
```

## Hinweis
Nach dem Cache-Reset prüfen, ob die App den Detektor mit der jetzt erkannten
Kamera (`/dev/video1`) sauber initialisiert.
