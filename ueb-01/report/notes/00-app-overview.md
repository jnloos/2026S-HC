# App-Überblick

## Ziel
Forschungs-Prototyp, der **drei Digital-Signage-Architekturvarianten** für die
LLM-gestützte Auswahl von Bildschirminhalten vergleicht:

- **V1 — edge-only:** Auswahl on-device über das lokale LLM-Brick (kein Cloud-LLM).
- **V2 — hybrid:** Auswahl in der Cloud (Claude) anhand strukturierter Kontext-Signale.
- **V3 — cloud-only:** Auswahl in der Cloud anhand eines Kamerabilds (+ optional Kontext).

Es geht ausdrücklich um den **Vergleich** (Latenz, Ort der Entscheidung,
Datenmenge), nicht um eine generische UNO-Q-Demo.

## Komponenten (Monorepo)
- **`arduino/`** — App für das **Arduino UNO Q** (App Lab; Dual-Brain-Board:
  Linux-MPU + STM32-MCU, Brick-Modell). Nur dieser Ordner wird aufs Board
  synchronisiert (`cli/rsync.sh`).
- **`api/`** — **FastAPI**-Dienst, simuliert ein kleines CMS (HTML-Snippets in
  „Pools") und stellt die drei Varianten-Endpunkte bereit.
- **`cli/`** — Bash-Skripte für das Board (`rsync.sh` Sync, `control.sh`
  Fernsteuerung der App per SSH/`arduino-app-cli`).
- **`web/`** — statische Assets für die optionale Debug-UI der API.

## Arduino-App: Strategy-Slot-Pipeline
`arduino/python/main.py` ist die Composition Root und verdrahtet je eine
Implementierung aus den Slots:

```
trigger ─► audience ─► picker ─► sink     (+ cms-Client)
```

- **triggers/** — `timer` | `person` (Personenerkennung per Video-Brick)
- **audience/** — Zielgruppen-Klassifikation (aktuell statisch)
- **pickers/** — `edge` | `hybrid` | `cloud` (= die drei Varianten)
- **sinks/** — Ausgabe (Web-UI-Brick rendert die gewählten HTML-Inhalte)
- **cms/** — HTTP-Client zur FastAPI

Varianten werden allein durch **Tausch des Pickers** gewählt — kein anderes
Modul kennt konkrete Varianten.

## Die drei Endpunkte (api/)
| Variante | Endpunkt | Eingabe |
|----------|----------|---------|
| V1 edge | `GET /pools/{id}` | — (Board wählt lokal) |
| V2 hybrid | `POST /pools/{id}/choose-by-context` | offenes JSON (beliebige Kontext-Keys) |
| V3 cloud | `POST /pools/{id}/choose-by-img` | Bild (multipart) + optional Kontext |

## Wissenswerte Eigenheiten
- **`personal:llm`** ist ein **vendored** Custom-Brick (`arduino/bricks/personal_llm/`),
  weil das Standard-`arduino:llm`-Brick sich nicht via App Lab installieren ließ.
  Liefert das on-device LLM für V1.
- **Prompts** sind Jinja2-Templates (`api/app/templates/*.j2`), nicht im Code.
- **Claude-Antworten** werden als JSON geparst + validiert (erfundene Content-IDs
  werden verworfen).
- **DB-Schema** via Alembic (kein Auto-Create); HTML-Snippets liegen als Dateien
  auf der Platte, nur Metadaten in der DB.
- **Board:** UNO Q, Versorgung im Testaufbau über VIN/5V-Pin, Zugang per WLAN/SSH,
  USB-C-Port frei für eine USB-Webcam (Logitech C270). → siehe Issue 01.
