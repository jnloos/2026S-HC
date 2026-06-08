# Dev-Debug-Fenster (Arduino Web-UI)

Eigenentwicklung, um im Betrieb zu sehen, **was im Arduino-Client passiert** —
und als **Messinstrument** für den Varianten-Vergleich (wo geht die Zeit hin:
On-Device-Inferenz vs. Netzwerk).

Aktiv, wenn `DEBUG=true` (Default). Wird per `config`-Message an den Browser
gemeldet; in Produktion (`DEBUG=false`) ist alles aus / No-op.

## 1. Live-Kamera-Preview (PiP)
- Kleines Vorschaufenster unten rechts, **Klick = Swap** (Vollbild ↔ Ecke), wie
  die Selbstansicht in Videochats.
- Technik: `VideoObjectDetection(..., camera_preview=True)` lässt das Brick den
  aktuellen Kameraframe liefern. Der `DebugStreamer` pollt den kontinuierlich
  aktualisierten Frame und sendet ihn als base64-JPEG-Data-URL über den
  WebUI-Websocket; das Frontend zeichnet ihn auf ein Canvas und legt erkannte
  Bounding-Boxen darüber (skaliert auf die native Kameraauflösung).
- Liefert ein durchgehendes Bild, nicht nur bei Detektionen.

## 2. Debug-Panel (Taste „D")
Eingeblendet links, getrennt vom Kamera-PiP. Quelle: ein strukturierter
Event-Kanal `debug_event` (`DebugBus`, no-op wenn Debug aus), gespeist an den
Nahtstellen der Pipeline.

Inhalte:
- **Status-Strip:** Variante, CMS-/LLM-/Kamera-Status (Punkte), Kamera-fps.
- **Pipeline-Runs (Timeline):** je Lauf gestapelte Balken pro Stufe
  (classify / select / publish) mit Dauer → zeigt sofort, wo die Zeit liegt.
- **Last decision:** Variante, Inferenzdauer, der **exakte Prompt**, die **rohe
  LLM-Antwort**, Kandidatenliste (gewählter hervorgehoben), Badges für
  `retried` / `fell back`.
- **Events & Logs:** CMS-Requests (Status/Latenz/Bytes) und ins Fenster
  weitergeleitete WARNING+-Logs (kein SSH nötig).

## Instrumentierte Nahtstellen (Backend)
- `pipeline/pipeline.py` — `run_started`, je Stufe `stage{dur_ms}`, `run_done{total_ms}`
- `pickers/edge.py` — `selection` (Prompt, Roh-Antwort, Kandidaten, retry/fallback, inference_ms)
- `cms/client.py` — `cms` je Request (Op, Status, Dauer, Bytes) + `healthy()`
- `main.py` — `DebugBus` verdrahtet, `HealthReporter`-Thread, `BusLogHandler` für Logs
- `debug/events.py` — `DebugBus`, `ms_since`, `BusLogHandler`, `HealthReporter`

## Nutzen für den Bericht
Das Fenster macht den Kern der Untersuchung sichtbar: Latenz-Aufteilung pro
Stufe und pro Variante, der tatsächlich gesendete Prompt/das Bild, und wo die
Entscheidung fällt (Gerät vs. Cloud).
