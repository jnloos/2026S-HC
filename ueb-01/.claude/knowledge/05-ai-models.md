# AI Models on the UNO Q

Several Bricks rely on **pre-trained AI models** that run **locally on the
board** (on the Linux/MPU side). No external service or extra hardware is needed
for on-device models — the App runs entirely on the UNO Q.

## How models bind to Bricks
- A Brick wraps a model and exposes a Python interface (e.g. `detect()`,
  `on_detect()`, classify, etc.).
- Once the App starts, the model is loaded and runs on the board.
- Some Bricks let you pick the model in `app.yaml`, e.g.:
  ```yaml
  bricks:
    - arduino:vlm:
        model: genie:qwen2_5_vl_7b_instruct
  ```

## Model task categories
- **Image recognition / object detection** — process camera frames or images to
  identify/locate objects (e.g. `object_detection`, `video_object_detection`,
  `image_classification`, `camera_code_detection`, `visual_anomaly_detection`).
- **Audio analysis** — keyword spotting, audio classification, speech-to-text
  (`keyword_spotting`, `audio_classification`, `asr`). Example wake words:
  "Hey", "Arduino".
- **Motion detection** — interpret IMU motion data (`motion_detection`,
  `gesture_recognition`, `vibration_anomaly_detection`).
- **Language / vision-language** — local LLM (`llm`), cloud LLM (`cloud_llm`),
  vision-language model (`vlm`).

## Local vs cloud
- **Local models** (most vision/audio Bricks, `llm`, `vlm`): run on-device,
  offline-capable, leverage the QRB2210 CPU/GPU/ISP.
- **Cloud models** (`cloud_llm` with e.g. `CloudModel.GOOGLE_GEMINI`): require
  network + credentials, but offload heavy generation.

Choose model selection in the App Lab AI Models UI or via the Brick's `app.yaml`
config / constructor args.
