# Feature: Echte On-Device-Zielgruppen-Erkennung (Audience Detection)

> **Nachtrag 2026-06-06 — Architekturwechsel: kein Sidecar mehr.** Die Inferenz
> läuft jetzt **in-process in der App** (`arduino/python/audience/inference.py`),
> nicht mehr als separater Docker-Container. Der FastAPI/ONNX-Sidecar
> (`detection/sidecar/`), `cli/sidecar.sh` und der HTTP-Client
> (`audience/sidecar_client.py`) wurden **entfernt**. Die ONNX-Modelle liegen
> jetzt mit der App unter `arduino/python/audience/models/` und werden via
> `rsync.sh` aufs Board synchronisiert. Aktivierung weiterhin über
> `AUDIENCE_MODE=face`; fehlen `onnxruntime`/`cv2` auf dem Board, fällt die App
> sauber auf den statischen Classifier zurück (`_make_audience_pipeline()` in
> `main.py`). Der untenstehende Text beschreibt den ursprünglichen
> Sidecar-Entwurf (historisch).

**Stand:** 2026-06-05. Software vollständig gebaut + lokal verifiziert; Board-Deployment
steht noch aus (Board zum Zeitpunkt der Arbeit per mDNS nicht erreichbar).

## Ziel
Den statischen Audience-Classifier (`arduino/python/audience/static.py`, der nur einen
fest konfigurierten `AUDIENCE_GROUP`-Wert zurückgibt) durch eine **echte,
kamerabasierte** Erkennung ersetzen. Statt des ursprünglich geplanten binären
„Kind anwesend?" liefert sie jetzt **Zielgruppen**: pro Gesicht **Altersband + Geschlecht**
und daraus eine aggregierte **Target Group** für die Content-Auswahl. Läuft zur Laufzeit
**ausschließlich on-device** (kein Cloud/Laptop in der Inferenz).

## Ansatz (nur Open-Source-Modelle)
1. **Gesichtserkennung:** **YuNet** (`face_detection_yunet_2023mar.onnx`, ~230 KB, liegt im
   OpenCV-Zoo, permissive Lizenz) — findet Gesichter im Kamera-Frame und liefert Crops.
   Ersetzt das unsichere Edge-Impulse-`lw-face-det.eim` aus dem alten Plan.
2. **Demografie-Klassifikator:** selbst trainiertes **MobileNetV3-small** mit **zwei Köpfen**
   (Alter 5 Bänder, Geschlecht 2 Klassen), trainiert auf **FairFace** (108k Gesichter,
   CC BY 4.0) auf YuNet-ausgerichteten Crops (Train-/Inferenz-Domäne gleich).
3. **Deployment:** beide Modelle laufen in **einem ONNX-Sidecar** (FastAPI + onnxruntime +
   OpenCV) auf dem Board — selbes Muster wie der llama.cpp-Sidecar (Container
   `face-classifier-runner:9998`, Netz `digsig-prototype_default`, Modell aus
   `~/audience-models/` gemountet, nativ auf dem Board gebaut → arm64, kein qemu).

## Komponenten (neu)
- **`detection/`** — Trainings-Subprojekt (Laptop, Python 3.12 via uv). Skripte (kein Notebook):
  `fetch_models` → `download_data` → `prepare` (YuNet-Crops) → `train` → `export_onnx` →
  `make_fixtures` → `sanity_infer`, verkettet in `scripts/run_all.sh`. Artefakte:
  `models/audience_classifier.onnx` + `labels.json` + `model_card.md`.
- **`detection/sidecar/`** — der On-Device-HTTP-Dienst. `POST /classify` (Roh-JPEG) →
  Audience-Dict; `GET /health`. Stub-Modus, wenn Modell fehlt. Dockerfile (`python:3.11-slim`).
- **`arduino/python/audience/`** — `FaceAudienceClassifier` (greift Frame vom Detector,
  POSTet an Sidecar, **wirft nie**), `FaceClassifierClient` (analog `cms/client.py`),
  `FrameGrabber` (cached den letzten JPEG-Frame). Verdrahtet in `main.py` über neues Setting
  **`AUDIENCE_MODE=static|face`** (Default bleibt `static`); `config.py` erweitert.
- **`cli/sidecar.sh`** — idempotentes Deploy (`push-model` → `build` → `up` → `health`),
  Muster wie `control.sh`. Kein manuelles SSH mehr.
- **`detection/e2e/`** — End-to-End-Test (Bild → Sidecar → API-Auswahl), ohne Kamera.

## Audience-Dict / Target Groups
Pro Zyklus ein scene-level Dict:
```json
{"people_count": 2, "faces": [{"age_band":"young-adult","gender":"female","age_conf":0.71,"gender_conf":0.93,"box":[x,y,w,h]}],
 "target_group": "young_women", "source": "face-sidecar"}
```
Altersbänder: `child · teen · young-adult · adult · senior`. Geschlecht: `male · female`.
**9 mögliche Target Groups:** `families_with_children` (sobald ein Kind erkannt wird — Priorität),
`young_women`, `young_men`, `adult_women`, `adult_men`, `teens`, `seniors`, `adults_mixed`,
`unknown` (kein Gesicht). Die Regeln stehen **datengetrieben** in `models/labels.json`
(`target_group_rules`) — umbenennbar/erweiterbar **ohne Retraining**.

## Modell-Ergebnisse (Validation, voller FairFace-Trainingslauf ~13 Epochen CPU)
- **Geschlecht:** ~89 % balanced accuracy.
- **Alter (5 Bänder):** ~62 % balanced accuracy (Random = 20 %).
- **Child-Recall:** ~79 % (das asymmetrisch wichtige Signal für die „Kinder"-Inhalte).
- ONNX 6,1 MB, Eingabe `1×3×112×112`, Ausgaben `age_logits`/`gender_logits`.

## Verifizierung (komplett lokal, ohne Board)
- **E1 — App-Unit-Tests** (`arduino/python/tests`): 9/9. Classifier wirft nie; korrekte Dicts.
- **E2 — Sidecar-Pipeline** (`detection/sidecar/tests`, echtes Modell + YuNet): 6/6.
  `child.jpg`→`families_with_children`, `young-adult_female.jpg`→`young_women`,
  `senior.jpg`→`seniors`, `noface.jpg`→`people_count=0`.
- **E3 — End-to-End bild-injiziert** (`detection/e2e`): Sidecar lokal (uvicorn) + API lokal
  (`dev.sh`-Stack) + Bakery-Seed. **Kind-Bild → `families_with_children` → Claude (V2) wählt
  Content-ID 4 „Kinder-Naschstation"**; **Erwachsene → ID 3 (nicht 4)**. Beweist die Kette
  *Demografie → Target Group → Content* ohne Kamera/Kind.

## Offen / Manueller Rest
- **Board-Deployment ausstehend:** `cli/sidecar.sh deploy` ausführen, sobald das Board wieder
  erreichbar ist; danach `configure.sh AUDIENCE_MODE=face ENABLE_CAMERA=true` + `control.sh restart`.
- **Einziger nicht-automatisierbarer Schritt:** 5-Minuten-Live-Kamera-Check (vor die Kamera
  stellen bzw. ausgedrucktes Foto) — siehe `detection/e2e/README.md`.

## Notizen / Fixes unterwegs
- **YuNet-Download:** opencv_zoo nutzt **Git LFS** → `raw.githubusercontent`-URL liefert nur den
  131-Byte-Pointer. Fix: `media.githubusercontent.com/media/...`-Endpoint (in `common.py`).
- **`run_all.sh`** reichte Pass-Through-Flags (`--subset`/`--epochs`) nicht durch (Array-/`local`-
  Bug, zsh-`mapfile`). Neu geschrieben + `RUN_ALL_DRYRUN=1` zum Testen. (Folge: der erste Lauf
  trainierte auf dem **vollen** Datensatz — willkommen, das ist das echte Modell.)
- **Ethik/Datenschutz:** Alter/Geschlecht aus Gesichtern sind **Schätzungen**, Geschlecht binär
  (Datensatz-Limit) — als Forschungssignal einordnen, nicht als Wahrheit. Steht im `model_card.md`.

## Wo die Daten liegen (Platzbedarf)
- `detection/.data/` (~2 GB, HF-Arrow) + `~/.cache/huggingface/` (~2 GB, Parquet) = FairFace,
  **doppelt** gespeichert (so arbeitet HF `datasets`). `detection/artifacts/` (~760 MB Crops),
  `detection/.venv/` (~1,7 GB). Alles bis auf `models/` ist **gitignored**. Der ~4-GB-Datensatz-
  Cache wird nur für ein erneutes Cropping/Training gebraucht und kann sonst gelöscht werden.
