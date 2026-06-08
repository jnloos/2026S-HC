# Audience classifier — model training

Trains an on-device **demographic audience classifier** (coarse age band +
binary gender) for the DigSig prototype. It is a two-headed **MobileNetV3-small**
trained on **FairFace** aligned face crops, exported to **ONNX**. The App runs
this **in-process** (`arduino/python/audience/inference.py`) — there is no
inference container.

This subproject produces three things the App's inference pipeline depends on:

- `models/audience_classifier.onnx` — the classifier.
- `models/face_detection_yunet_2023mar.onnx` — the YuNet face detector (shared).
- `models/labels.json` — the frozen label/preprocessing/output contract.

> Scope: everything here lives under `detection/` (`scripts/`, `models/`,
> `artifacts/`). The trained models are consumed by the App; **after a retrain,
> copy them into `arduino/python/audience/models/`** so they ship with the App.
> `make_fixtures.py` writes test fixtures under `arduino/python/tests/fixtures/`.

## The frozen contract (do not change without coordinating)

ONNX model:

| | name | shape |
|---|---|---|
| input | `input` | `[N, 3, 112, 112]` (dynamic batch `N`), RGB |
| output | `age_logits` | `[N, 5]` |
| output | `gender_logits` | `[N, 2]` |

- Preprocessing: RGB, resize 112×112, `/255`, normalize
  `mean=[0.485,0.456,0.406] std=[0.229,0.224,0.225]` (ImageNet).
- Age bands (output order): `["child","teen","young-adult","adult","senior"]`.
- Genders (output order): `["male","female"]`.
- opset ≥ 13.

All of this is emitted into `models/labels.json`; the App reads it rather
than hard-coding values.

### FairFace age bin → band

| FairFace age | band |
|---|---|
| `0-2`, `3-9` | child |
| `10-19` | teen |
| `20-29` | young-adult |
| `30-39`, `40-49`, `50-59` | adult |
| `60-69`, `more than 70` | senior |

Gender: FairFace `Male`/`Female` → `male`/`female`.

## Reproduce

Python **3.12**, CPU-only. Using [`uv`](https://docs.astral.sh/uv/):

```bash
cd detection

# 1. create the venv
uv venv --python 3.12 .venv

# 2. install torch/torchvision from the CPU index, then the rest
uv pip install --python .venv/bin/python torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python -r requirements.txt

# 3. run the whole pipeline on a subset (fast smoke run)
bash scripts/run_all.sh --subset 8000
```

`run_all.sh` runs, in order:
`fetch_models → download_data → prepare → train → export_onnx → make_fixtures →
sanity_infer`, forwarding `--subset` / `--max-train` to the stages that accept
them.

Every script is independently runnable and self-documenting:

```bash
.venv/bin/python scripts/train.py --help
.venv/bin/python scripts/export_onnx.py --int8        # optional int8 model
```

### Individual stages

| script | what it does |
|---|---|
| `scripts/fetch_models.py` | download shared YuNet detector (idempotent) |
| `scripts/download_data.py` | load FairFace via HF `datasets`, print class distribution |
| `scripts/prepare.py` | YuNet-crop faces → `artifacts/crops/{split}/*.jpg` + `labels.csv` |
| `scripts/train.py` | train two-headed MobileNetV3-small, save `artifacts/best.pt` + `metrics.json` |
| `scripts/export_onnx.py` | export ONNX + write `labels.json` + `model_card.md` |
| `scripts/make_fixtures.py` | export labeled test fixtures into `arduino/python/tests/fixtures/` |
| `scripts/sanity_infer.py` | onnxruntime smoke test on crops + fixtures |

All scripts use a **fixed seed (42)** and write JSON metrics where applicable.

## Expected artifacts

```
models/
  audience_classifier.onnx
  audience_classifier.int8.onnx     # only with export_onnx.py --int8
  face_detection_yunet_2023mar.onnx
  labels.json
  model_card.md
artifacts/
  crops/{train,validation}/*.jpg
  crops/labels.csv
  best.pt
  metrics.json
arduino/python/tests/fixtures/             # written by make_fixtures.py
  child.jpg young-adult_male.jpg young-adult_female.jpg senior.jpg noface.jpg
  fixtures_labels.json
```

`.venv/`, `.data/` and `artifacts/` are gitignored.

## Accuracy expectation (be honest)

This is a **coarse** classifier for **aggregate** audience signals, not a
per-person identifier. Realistic targets on a properly-sized FairFace run:

- Gender head: high accuracy (FairFace gender is well-separated).
- Age head: **macro accuracy roughly 80–90%** across the 5 coarse bands, with
  the usual confusion between adjacent bands (teen↔young-adult,
  adult↔senior).
- **Child-band recall is the priority metric** — the pipeline keys
  "families with children" off it — so model selection optimizes child recall
  (fallback: balanced accuracy) and training uses an age-balanced sampler.

Small `--subset` runs will underperform these numbers; they exist for fast
iteration, not final quality.

## ETHICS / limitations

- Outputs are **estimates, not ground truth.** Age/gender are inferred from
  appearance and will be wrong for many people. Never use for identity, access,
  eligibility, or any consequential per-person decision.
- **Binary gender is a modeling limitation**, not a claim about gender. The
  FairFace label space is binary; the model cannot represent non-binary or
  other identities and will mislabel people.
- Demographic estimators have known **accuracy disparities across skin tone,
  age and presentation**. FairFace is race-balanced to reduce this, but bias
  remains. Use only for aggregate, non-identifying signals.
- The on-device pipeline stores no images; classification is ephemeral.
- Dataset: **FairFace**, license **CC BY 4.0** (Karkkainen & Joo).
