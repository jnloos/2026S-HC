# Audience Classifier (on-device demographic estimator)

Two-headed **MobileNetV3-small** estimating a coarse **age band** and a
**binary gender** from an aligned 112x112 face crop. Trained for the
ARDU-DigSig-Prototype detection pipeline; exported to ONNX for the
on-device sidecar.

## Dataset
- **FairFace** (HuggingFace `HuggingFaceM4/FairFace`).
- **License: CC BY 4.0** (FairFace). Attribution: Karkkainen & Joo, "FairFace:
  Face Attribute Dataset for Balanced Race, Gender, and Age".

## Label mapping (frozen spec)
- Age bands (output order): ['child', 'teen', 'young-adult', 'adult', 'senior']
- Genders (output order): ['male', 'female']
- FairFace age bin -> band:
  - child: `0-2`, `3-9`
  - teen: `10-19`
  - young-adult: `20-29`
  - adult: `30-39`, `40-49`, `50-59`
  - senior: `60-69`, `more than 70`
- FairFace gender `Male`/`Female` -> `male`/`female`.

## Input / preprocessing
- Input tensor `input`: `[N, 3, 112, 112]`, RGB.
- `/255`, then normalize mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225] (ImageNet).
- Face crop produced by YuNet (`face_detection_yunet_2023mar.onnx`), largest
  face, box expanded ~20%.

## Outputs
- `age_logits`: `[N, 5]` (argmax over age bands above).
- `gender_logits`: `[N, 2]` (argmax over genders above).

## Metrics (validation, best checkpoint)
- Selected epoch: 6
- Age head balanced accuracy: 0.621
- Age macro recall: 0.621
- Child-band recall (priority metric): 0.786
- Gender head balanced accuracy: 0.879


## ETHICS / limitations
- These are **estimates, not ground truth.** Age band and gender are inferred
  from facial appearance and will be wrong for a meaningful fraction of people.
  Do not use for identity, access, eligibility, or any consequential decision
  about an individual.
- **Binary gender is a modeling limitation**, not a statement about gender. The
  FairFace label space is binary; this model cannot represent non-binary or
  other gender identities and will mislabel many people.
- Demographic estimators carry known **accuracy disparities across skin tone,
  age and presentation**. FairFace is race-balanced to mitigate this, but
  residual bias remains. Use only for aggregate, non-identifying audience
  signals (e.g. "show family content"), never per-person.
- No images are stored by the on-device pipeline; classification is ephemeral.
