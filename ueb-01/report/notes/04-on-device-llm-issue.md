# Issue + Lösung: On-Device-LLM auf diesem UNO Q (Variante 1)

**Status:** gelöst per Workaround — On-Device-LLM läuft via llama.cpp-Sidecar.
Funktioniert, ist aber langsam (Board-CPU, kein NPU). Stand 2026-06-04.

## Symptom (Ausgangslage)
V1 (edge-only) soll lokal per On-Device-LLM den Content auswählen. Der
`EdgeSelector` scheiterte bei jedem Lauf:
```
LargeLanguageModel: Model 'qwen3_4b_instruct_2507' not found ... models: []
httpx.ConnectError: [Errno -2] Name or service not known   # genie-models-runner
pickers.base.SelectorError: local LLM call failed: ...
```

## Ursache (Hardware-/Plattform-Gating, kein Code-Bug)
Das Board ist ein **`Arduino UnoQ`** (Board-ID `unoq`), **nicht** `ventunoq`
(die Variante mit Qualcomm-Hexagon-cDSP/NPU). Arduinos On-Device-GenAI-Stack ist
durchgängig `ventunoq`-only und setzt Hardware voraus, die hier fehlt
(`/dev/fastrpc-cdsp`, `/usr/share/qcom` — vorhanden ist nur `/dev/fastrpc-adsp`).
Belege (aktive Assets `/var/lib/arduino-app-cli/assets/0.10.1/`):
- `models-list.yaml`: die einzigen LLM/VLM-Modelle (`genie:qwen3_4b_instruct_2507`,
  `genie:qwen2_5_vl_7b_instruct`) sind `supported_boards: ["ventunoq"]`. **Kein**
  LLM-Modell ist für `unoq` freigegeben.
- `bricks-list.yaml`: `arduino:llm` ist `ventunoq`-only + `requires_services:
  [arduino:genie]`. Daher listet `arduino-app-cli brick list` für `unoq` als
  einzige LLM-Brick nur **`arduino:cloud_llm`** (Cloud!).
- `services/arduino/genie/service_compose.yaml`: mountet das fehlende
  `/dev/fastrpc-cdsp` + `/usr/share/qcom`, Image `genie-models-runner` ist nicht
  gezogen.

Deckt sich mit der CLAUDE.md-Notiz, dass die Stock-`arduino:llm`-Brick „sich
nicht via App Lab installieren ließ" → daher die vendored `personal:llm`-Brick.
**Ein offizielles On-Device-LLM ist auf genau diesem Board nicht möglich.**

## Lösung: llama.cpp-Sidecar (echte On-Device-CPU-Inferenz)
Die vendored Brick (`personal_llm/local_llm.py`) hat bereits einen
`llamacpp:`-Codepfad → Host `llamacpp-models-runner`, Port 9999, OpenAI-`/v1`.
Wir betreiben einen generischen llama.cpp-Server als Sidecar — **keine
Code-Änderung in der Brick nötig, nur Konfiguration**:

1. Image (arm64) ziehen: `docker pull ghcr.io/ggml-org/llama.cpp:server`.
2. Modell: **Qwen2.5-0.5B-Instruct Q4_K_M** GGUF (~469 MB) nach
   `~/llm-models/qwen0.5b.gguf` (HF: `Qwen/Qwen2.5-0.5B-Instruct-GGUF`).
3. Sidecar im App-Docker-Netz starten (Name muss exakt `llamacpp-models-runner`
   sein, damit die Brick ihn per DNS findet):
   ```bash
   docker run -d --name llamacpp-models-runner \
     --network digsig-prototype_default --restart unless-stopped \
     -v ~/llm-models:/models:ro ghcr.io/ggml-org/llama.cpp:server \
     -m /models/qwen0.5b.gguf --alias qwen0.5b --host 0.0.0.0 --port 9999 \
     -c 4096 -t 4 --no-mmap
   ```
   - `--no-mmap`: lädt die Gewichte komplett ins RAM (passt: ~862 MB frei) →
     kein langsames Paging vom eMMC während der Inferenz.
   - `--alias qwen0.5b`: muss zur Brick-Config `model: llamacpp:qwen0.5b` passen
     (`brick_config.yaml`).
4. `arduino/bricks/personal_llm/brick_config.yaml`: `model: llamacpp:qwen0.5b`.

**Wichtig:** Der Sidecar läuft *außerhalb* von App Lab. Ein
`arduino-app-cli app stop/start` lädt die Python-App nicht neu — Neustart per
`docker restart digsig-prototype-main-1` (siehe Notiz 05).

## Performance (gemessen auf dem Board)
Reine Inferenz (4× aarch64 A53, kein NPU), Qwen2.5-0.5B Q4:
- **Prompt-Eval: ~6–7.5 tok/s** (~140 ms/Token)
- **Generierung: ~1.4–1.8 tok/s** (~600 ms/Token) — sehr langsam pro Token.

### Optimierungs-Reihe (Code in `pickers/edge.py` + `main.py`) und Wirkung
Latenz pro V1-Auswahl, schrittweise reduziert:
1. **Ausgangslage** (JSON-Antwort + 600 Zeichen HTML/Kandidat → ~1500-Token-Prompt,
   ~87 Token Antwort): **~230 s**, oft Timeout.
2. **HTML aus dem Prompt entfernt** (`_SNIPPET_PREVIEW_CHARS = 0`; nur Name +
   Beschreibung, die laut CLAUDE.md das Signal ist) → ~595-Token-Prompt: **~140 s**.
3. **Nur-ID-Antwort statt JSON** (Modell gibt bloß die Integer-ID zurück,
   `max_tokens=16`, `temperature=0`): Generierung 87 → **2 Token** (~60 s → ~0.7 s),
   und **keine JSON-Parsing-Fehler/Retries/Fallbacks** mehr → **~80 s** (jetzt
   reine Prompt-Eval).
4. **Prompt-Prefix-Caching**: stabilen Teil (System + Kandidatenliste) **zuerst**,
   variablen Kontext **zuletzt** in den Prompt; llama.cpp mit `-np 1`
   (ein Slot) + `--cache-reuse 256`. Der KV des Kandidaten-Prefixes wird
   wiederverwendet → Folge-Auswahlen evaluieren statt 580 nur **~54 Token**:
   **~20 s** (Folgeläufe), erster (kalter) Lauf weiterhin ~96 s.

**Endstand:** erste Auswahl ~96 s (kalt), danach **~20 s** je Auswahl. Ohne den
parallel laufenden EI-Kamera-Runner (CPU-Konkurrenz; drückt auf ~2.6 tok/s) wäre
eine gecachte Auswahl ~8 s — d.h. Kamera/Detektor und LLM teilen sich die 4 Kerne.

### Qualität (gemessen — der eigentliche Knackpunkt)
Mit der Nur-ID-Antwort liefert das 0.5B-Modell zuverlässig eine gültige ID
(saubere Ausgabe `[id=3]`/`4`/`5`, kein JSON-Fallback mehr).

**Auswahl­qualität (5 klar gelagerte Kontexte gegen die Bakery-Fixtures):
3/5 korrekt.**
- ✅ heiß/sonnig/junge Erwachsene → id 3 (Eiskaffee)
- ✅ Kinder/Familie → id 4 (Kinder-Naschstation)
- ✅ Senioren/Nachmittag → id 5 (Kaffeeklatsch)
- ❌ früher Morgen/Pendler → id 3 statt 1 (Frühstück)
- ❌ kalt/regnerisch/Mittag → id 4 statt 6 (Suppe)

Das 0.5B trifft die **offensichtlichen** Fälle, scheitert aber an solchen mit
etwas mehr Schlussfolgerung, und zeigt Positions-/Wiederholungs-Bias (zweimal
id 3, zweimal id 4). **Konsequenz:** ein *kleineres* Modell (360M/135M) würde
mit hoher Wahrscheinlichkeit unter diese 3/5 fallen — also **nicht** verkleinern.
Das 0.5B ist die sinnvolle On-Device-Untergrenze und für eine *rigorose*
V1-Qualitätsbewertung bereits grenzwertig. Für belastbare Auswahlqualität:
größeres Modell (genie-Qwen-4B auf `ventunoq`/NPU) oder die Cloud-Varianten
V2/V3 (Claude). Reasoning entfällt in V1 (nur ID nötig).

### Weitere Hebel (offen)
- **Kleineres Modell** (z.B. SmolLM2-360M/135M): senkt Prompt-Eval + Kaltstart
  ~1.5–3×, Qualitätsrisiko steigt.
- **Kamera/Detektor während V1-Timer-Eval aus** (vermeidet CPU-Konkurrenz):
  gecachte Auswahl → ~8 s. Achtung: EI-Runner *stoppen* erzeugt einen
  Detektor-Retry-Sturm (DNS-Spam, frisst CPU) — sauberer wäre, den Detektor per
  Setting gar nicht zu konstruieren.
- **`ventunoq`-Board** mit nativem genie-Stack (NPU) für echte Edge-Performance.

## Fazit für den Bericht
Sauber trennen: **Board-Eigenschaft (`unoq` ohne NPU), kein Software-Mangel.**
V1 „edge-only" ist auf diesem Board nur per CPU-llama.cpp-Workaround lauffähig —
funktional korrekt, aber ~2 min/Auswahl und qualitativ durch das 0.5B-Modell
limitiert.
