# Report-Notizen

Sammlung von Notizen für den späteren Kurzbericht — Wissenswertes zur App und
die Issues, auf die wir gestoßen sind. Roh-Material, kein fertiger Bericht.

| Notiz | Inhalt |
|-------|--------|
| [00-app-overview.md](00-app-overview.md) | Was die App ist: 3-Varianten-Vergleich, Komponenten, Pipeline |
| [01-usb-host-camera-issue.md](01-usb-host-camera-issue.md) | **Hauptproblem:** USB-Kamera am UNO Q wird nicht erkannt — Ursache + Fix |
| [02-debug-window.md](02-debug-window.md) | Dev-Debug-Fenster (Live-Kamera-Preview + Pipeline-Instrumentierung) |
| [03-sketch-build-cache-error.md](03-sketch-build-cache-error.md) | Issue: korrupter Sketch-Build-Cache beim App-Restart (offen) |
| [04-on-device-llm-issue.md](04-on-device-llm-issue.md) | Issue+Lösung: kein offizielles On-Device-LLM auf diesem `unoq`-Board (V1) — Ursache, llama.cpp-Workaround, gemessene Performance |
| [05-integration-fixes.md](05-integration-fixes.md) | Full-Stack-Integration: Caddy-Proxy, App-Neustart via docker, socket.io-Client, Debug-config-Rebroadcast, Tooling |
| [06-audience-detection.md](06-audience-detection.md) | **Feature:** echte On-Device-Zielgruppen-Erkennung (YuNet + FairFace-MobileNetV3 → Alter/Geschlecht → Target Group), ONNX-Sidecar, App-Integration, lokale E2E-Verifizierung |
| [uno-q-usb-host-problem.md](uno-q-usb-host-problem.md) | Frühere USB-Host-Problembeschreibung (VBUS-Vermutung); durch [01-usb-host-camera-issue.md](01-usb-host-camera-issue.md) inzwischen aufgelöst. |

Verwandte Doku im Repo:
- `.claude/knowledge/` — UNO-Q-/App-Lab-Wissensbasis.
