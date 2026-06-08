# Plan: Echte On-Device-Zielgruppen-Erkennung (Audience Detection)

> Arbeitsplan zum Weitermachen. Stand: 2026-06-04 (abends pausiert).
> Ziel: V1/V2 sollen statt eines statisch konfigurierten `AUDIENCE_GROUP="general"`
> einen **echten, kamerabasierten** Zielgruppen-Kontext bekommen.

## Ausgangslage / Warum
Aktuell liefert `arduino/python/audience/static.py` (`StaticAudienceClassifier`)
nur einen festen Wert aus der Env — **keine echte Erkennung**. Die Kamera
(`video_object_detection`) macht nur Personen-Präsenz (Trigger), keine Demografie.
Echte Zielgruppen-Ableitung gibt es bisher nur in **V3** (Claude-Vision, Cloud).
Architektur ist vorbereitet: neue `AudienceClassifier`-Implementierung schreiben
und in `main.py` gegen `StaticAudienceClassifier` tauschen — Rest der Pipeline
bleibt unangetastet.

## Erstes Ziel (bewusst klein & messbar)
**Binär: „Kind anwesend" vs. „nur Erwachsene".** Genau das, was die Bakery-
Fixture „Kinder-Naschstation" (id 4) braucht. Fein-granulares Alter ist zu hart
und unzuverlässig — später optional.

## Gewählter Ansatz (geklärt im Gespräch)
**Face-Crop-Pipeline + kleiner CNN-Klassifikator, trainiert auf FairFace,
deployt als ONNX-Sidecar.**
1. **`lw-face-det.eim`** (Gesichtsmodell, für `unoq` im Katalog) detektiert
   Gesichter im Kamera-Frame → Crops.
2. Jeder Gesichts-Crop geht an einen **kleinen Klassifikator** (MobileNetV3-small,
   2 Klassen child/adult).
3. Ergebnis aggregiert → Pipeline-Kontext, z.B.
   `{"child_present": bool, "people_count": N, "group": "...", "confidence": …,
   "source": "face-classifier"}`.

**Warum FairFace:** 108.501 Bilder, ausgeglichene Alters-Bins (0-2, 3-9, 10-19 …
70+) + Geschlecht, **CC BY 4.0** (kommerziell ok mit Attribution; UTKFace ist nur
Forschung). Bins → binär mappen: **0–9 = Kind, 20+ = Erwachsen, 10–19 aussparen.**
Bezug: GitHub `joojs/fairface`, Hugging Face `HuggingFaceM4/FairFace`
(automatisch per `datasets`-Lib ziehbar, kein manueller Drive-Download).

**Warum das den Domain-Gap löst:** Training auf *ausgerichteten Gesichts-Crops*,
zur Laufzeit ebenfalls Crops (via lw-face-det) → gleicher Input-Typ. Viel besser
als ein auf Voll-Stockfotos (Pexels) trainiertes Modell.

**Läuft das auf dem Board?** Ja, klar — das Board lässt schon live ein CNN
(YoloX-Objekterkennung) laufen; ein 2-Klassen-MobileNet ist ~1000× billiger als
das 0.5B-LLM (ms-Bereich, wenige MB RAM). Kein LLM-Latenzproblem.

## Schrittplan
**Phase 1 — Machbarkeit / Mini-Training (Laptop)**
- [ ] Laptop-Compute prüfen (GPU? sonst CPU — kleines Transfer-Learning reicht).
- [ ] venv mit `torch`/`torchvision` (oder `tensorflow`), `datasets`, `onnx`.
- [ ] FairFace via Hugging Face laden; Labels Alters-Bin → binär (child/adult),
      10–19 droppen; Train/Val-Split.
- [ ] MobileNetV3-small (vortrainiert) + 2-Klassen-Kopf, kurz fine-tunen.
- [ ] **Val-Accuracy ehrlich berichten** (Erwartung: brauchbar, nicht perfekt).

**Phase 2 — Export**
- [ ] Bestes Modell → **ONNX** (ggf. int8-Quantisierung), Inferenz-Sanity-Check.
- [ ] Mini-Inferenz-Test (ein paar Crops) lokal.

**Phase 3 — Board-Deployment (ONNX-Sidecar, Muster wie llama.cpp)**
- [ ] arm64-Container mit `onnxruntime` + kleinem HTTP-Wrapper (Crop rein →
      {label, conf} raus), Name z.B. `face-classifier-runner` im App-Netz
      `digsig-prototype_default`. Modell-Datei nach `~/llm-models/` o.ä. mounten.
- [ ] CPU-Latenz auf dem Board messen.

**Phase 4 — Integration (Arduino-App)**
- [ ] `lw-face-det` verfügbar machen (Brick/Modell konfigurieren) — Gesichts-Crops
      aus dem Frame holen.
- [ ] Neue `arduino/python/audience/face.py` → `FaceAudienceClassifier`:
      Frame → Gesichter → Crops → Sidecar → aggregiertes Audience-Dict.
- [ ] In `main.py` `StaticAudienceClassifier` durch den neuen ersetzen
      (idealerweise per Setting umschaltbar, z.B. `AUDIENCE_MODE=static|face`).
- [ ] `ENABLE_CAMERA=true` nötig.

**Phase 5 — Evaluierung**
- [ ] V2 (Cloud-Auswahl) mit echtem Audience-Kontext testen — sollte jetzt die
      Kinder-Naschstation wählen, wenn ein Kind im Bild ist.
- [ ] V1 (Edge-LLM) testen — Achtung CPU-Konkurrenz (Klassifikator selbst leicht,
      aber 0.5B-LLM bleibt langsam).
- [ ] Ergebnis in `report/notes/` dokumentieren (inkl. Genauigkeit + Caveats).

## Offene Entscheidungen / Notizen
- **Deploy-Weg:** ONNX-Sidecar (gewählt, voll automatisierbar) vs. EIM über
  `arduino:image_classification` (nativer, evtl. QNN-Beschleunigung, aber
  EI-Studio-Konvertierung nötig). Sidecar zuerst; EIM als Option offen.
- **Daten:** FairFace primär. Optional ergänzen: Kaggle „Children vs Adults"
  (Voll-Szenen, schneller binärer PoC) oder UTKFace (nur Forschung).
- **Ethik/Datenschutz fürs Paper:** Demografie-Inferenz aus Gesichtern ist
  fehleranfällig und sensibel — sauber einordnen, nicht überverkaufen.

## Datensätze (recherchiert, Lizenz verifiziert)
| Datensatz | Labels | Umfang | Lizenz |
|---|---|---|---|
| **FairFace** ⭐ | Alter (9 Bins), Geschlecht, Race; ausgeglichen | 108.501 | CC BY 4.0 |
| UTKFace | Alter 0–116, Geschlecht, Ethnie | ~23k | nur Forschung |
| Adience | 8 Alters-Gruppen, Geschlecht | ~26k | Benchmark |
| IMDb-WIKI | Alter/Geschlecht (verrauscht) | ~500k | Pretraining |
| Kaggle „Children vs Adults" | binär (Voll-Szene) | klein | PoC |

Links: github.com/joojs/fairface · huggingface.co/datasets/HuggingFaceM4/FairFace ·
susanqq.github.io/UTKFace · kaggle.com/datasets/die9origephit/children-vs-adults-images

## Wo das Gesamtsystem gerade steht (zum Wiedereinsteigen)
- **V1 edge** läuft: On-Device-LLM via **llama.cpp-Sidecar** (`llamacpp-models-runner:9999`,
  Qwen2.5-0.5B Q4), nur-ID-Antwort, Prompt-Prefix-Cache. Latenz ~9–100s, Qualität
  3/5. Board aktuell in **`ENABLE_CAMERA=false`** (schnelle V1-Eval) + Timer.
- **V2/V3** (API, Cloud-Claude) live getestet, funktionieren gut (V2 picks 3/3).
- Plumbing/Tooling/Fixes: siehe `report/notes/04` (LLM) und `report/notes/05`
  (Integration: Caddy, docker-restart, socket.io, Re-Broadcast, dev.sh).
- **Achtung:** etliche unkommittete Änderungen im Working Tree (ganze Session).
  Morgen ggf. zuerst committen.
- Für die Audience-Arbeit: `ENABLE_CAMERA=true` setzen (`./cli/configure.sh
  ENABLE_CAMERA=true`) und den EI-Runner wieder starten.
