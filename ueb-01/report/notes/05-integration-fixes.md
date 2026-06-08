# Integration & Setup: Stolpersteine + Fixes (Full-Stack-Betrieb)

Sammlung der Probleme, die beim Verbinden von **Board-Client ↔ Laptop-CMS ↔
Debug-UI** auftraten, und wie sie gelöst wurden. Kontext: API (FastAPI) läuft auf
dem Laptop, der Arduino-Client auf dem Board. Stand 2026-06-04.

## 1. Board ↔ Laptop-API: Reverse-Proxy statt offenem Port
Auf dem Board ist `localhost` das Board selbst — der Client muss die Laptop-IP
ansprechen. Die ufw des Laptops blockierte Port 8000. **Lösung:** uvicorn bleibt
unprivilegiert/intern auf `127.0.0.1:8000`, und **Caddy** auf dem Laptop frontet
Port 80 und leitet `/digsig/*` → `127.0.0.1:8000` weiter (Prefix wird gestrippt).
Board-Client nutzt `CMS_URL=http://<laptop-ip>/digsig`. Kein offener Extra-Port,
kein Binden privilegierter Ports durch die App.
- Die Laptop-IP wechselt im LAN → **Auto-Erkennung** (`ip route get`) in
  `cli/dev.sh` / `cli/configure.sh`, nie von Hand setzen.
- `arduino/python/config.py` lädt eine optionale `runtime.env` (KEY=VALUE,
  gitignored) und überschreibt damit die Umgebung → so kommt `CMS_URL` aufs
  Board, ohne App-Lab-Env zu editieren (App Lab hat dafür keinen CLI-Hebel).

## 2. App-Neustart lädt den Code NICHT neu
`arduino-app-cli app stop/start` startet den Python-Container **nicht** neu
(der Container lief 2 h durch, las weder `runtime.env` noch geänderte `assets/`
ein) und meldet danach fälschlich `App Is Running`. **Lösung:**
`docker restart digsig-prototype-main-1` (re-exec von `main.py`). In
`cli/control.sh restart` eingebaut (Container-Name per `docker ps -a` ermittelt,
damit auch ein gestoppter Container gefunden wird).

## 3. Frontend: socket.io-Client fehlte
Konsole: `GET /socket.io/socket.io.js 400` + `io is not defined`. Der `web_ui`-
Brick (python-socketio 5.16) liefert **keinen** Client unter `/socket.io/...` —
diese URL ist der Protokoll-Endpunkt (400 ist erwartbar). **Lösung:** den
socket.io-Client lokal bündeln (`assets/socket.io.min.js`, v4.7.5 — passt zum
Server-Protokoll) und per `<script src="socket.io.min.js">` laden. Der ältere,
nicht synchronisierte Stand des Boards war die eigentliche Fehlerquelle.

## 4. Debug-`config` nur einmalig → spät verbundene Tabs „tot"
Der `config`-Handshake (aktiviert Debug-PiP/-Panel) wurde nur einmal beim
App-Start gesendet. Ein Browser, der **danach** verbindet (Normalfall), verpasste
ihn → das gesamte Debug-UI blieb inaktiv (alle Debug-Events sind clientseitig auf
`debugEnabled` gegated). **Lösung:** `HealthReporter` sendet `config` periodisch
neu → spät verbundene Tabs bekommen ihn innerhalb eines Intervalls.

## 5. Kleinkram
- iframe-Sandbox-Warnung: `allow-same-origin` entfernt (Content-Snippets brauchen
  es nicht) → Konsole sauber.
- favicon-404: Inline-SVG-Favicon.
- `dev.sh`-PID-Handling: `python -m uvicorn` (damit `$!` = uvicorn-Prozess) +
  `pkill`-Backstop gegen verwaiste Instanzen (sonst „address already in use").

## Tooling, das dabei entstand
- `cli/dev.sh up|down|status|logs` — fährt den ganzen Stack hoch (API starten,
  Laptop-IP erkennen, Board konfigurieren, syncen, App neustarten).
- `cli/configure.sh` — schnelle Board-Rekonfiguration (`CMS_URL`, `TRIGGER_MODE`,
  `TIMER_INTERVAL_SEC`, …), Auto-IP.
- Doku: `.claude/knowledge/09-dev-workflow.md`.

## Kontroll-Runde: was live getestet wurde (alles bestanden)
Ausgiebige End-to-End-Kontrolle des laufenden Systems:

- **V1 edge** (Board, On-Device-LLM): Trigger → Audience → CMS-Pool → Selector →
  Render, echte Picks, Content rendert im iframe. Latenz/Qualität siehe Notiz 04.
- **V2 hybrid** (`POST /pools/1/choose-by-context`, echte Claude-Calls): 200,
  **kontextpassende** Picks (heiß→Eiskaffee #3, Kinder→#4, Pendler→Frühstück #1).
  Robust gegen leere/irrelevante Bodies (kein 500).
- **V3 cloud** (`POST /pools/1/choose-by-img`, Multipart-Feld `image` + optional
  `context`): 200, Vision-Pfad wählt gültige ID. (Beobachtung: Wetter-Cue im Bild
  dominierte den schwachen Audience-Cue — Tuning-Frage, kein Bug.)
- **Validierung**: `services/selection.py` weist erfundene IDs ab; alle Antworten
  blieben in-pool.
- **Fehler-/Edge-Fälle**: nicht-existenter Pool → sauberes 404; fehlendes Bild →
  422; leeres Bild → 400; kaputtes JSON-Context → 400; **keine 500er**.
- **API-Debug-UI** (`/debug`): Index + Static + `/recent` (Backfill) + `/stream`
  (SSE live) funktionieren; Bus erfasst V2/V3-Events inkl. `image_meta`.
  (Kosmetik: externes FastAPI-Favicon liefert 403.)
- **Board-Debug-UI**: D-Taste togglet Panel, PiP-Swap, Health-Dots korrekt
  (CAM=rot bei `ENABLE_CAMERA=false`), Run-Timeline + Decision-Panel füllen sich
  live, Content rotiert, **Konsole durchgehend 0 Fehler/0 Warnungen**. (Run-
  Timeline/Decision werden nicht re-broadcastet → ein frisch verbundener Tab
  zeigt sie erst beim nächsten Lauf; bewusst, da Live-Events.)
- **54 API-Tests** grün.

Einzige verbleibende Einschränkung: On-Device-LLM-Latenz/-Qualität auf diesem
Board (Notiz 04) — kein Software-Defekt.
