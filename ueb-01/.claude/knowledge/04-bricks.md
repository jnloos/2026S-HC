# Bricks — the building blocks

**Bricks** are pre-built **code building blocks** for Apps. They expose complex
functionality (AI models, networking, web UI, storage, cloud, audio) through a
few lines of Python. They run on the **Linux/Python side** and are imported into
`main.py`.

## How to use a Brick
1. **Add it in App Lab**: inside an App click **"Add Brick"**, pick from the list
   (the list is updated frequently; the canonical list lives in the App Lab
   **Bricks** section with per-Brick API docs).
2. It gets declared in `app.yaml` under `bricks:` (e.g. `arduino:web_ui`).
3. **Import + use** it in `main.py`:
   ```python
   from arduino.app_bricks.weather_forecast import WeatherForecast
   forecaster = WeatherForecast()
   forecast = forecaster.get_forecast_by_city("London")
   ```

Some Bricks accept config in `app.yaml`, e.g. choosing an AI model:
```yaml
bricks:
  - arduino:vlm:
      model: genie:qwen2_5_vl_7b_instruct
```

## Brick catalog

Brick IDs (`app.yaml`) and their Python import paths, observed in the official
`app-bricks-examples` repo (App Lab ~0.7). The Bricks section in App Lab is the
authoritative, always-current list.

| `app.yaml` id | Python import | Class(es) | Purpose |
|---------------|---------------|-----------|---------|
| `arduino:web_ui` | `arduino.app_bricks.web_ui` | `WebUI` | Host a local web server, serve `assets/`, message the browser |
| `arduino:object_detection` | `arduino.app_bricks.object_detection` | `ObjectDetection` | Detect objects in a still image |
| `arduino:video_object_detection` | `arduino.app_bricks.video_objectdetection` | `VideoObjectDetection` | Real-time object/face detection on a video stream |
| `arduino:video_image_classification` | `arduino.app_bricks.video_imageclassification` | `VideoImageClassification` | Real-time image classification on video |
| `arduino:image_classification` | `arduino.app_bricks.image_classification` | `ImageClassification` | Classify a still image |
| `arduino:camera_code_detection` | `arduino.app_bricks.camera_code_detection` | `CameraCodeDetection`, `Detection`, `draw_bounding_box` | Detect QR/barcodes from camera |
| `arduino:visual_anomaly_detection` | `arduino.app_bricks.visual_anomaly_detection` | `VisualAnomalyDetection` | Detect visual defects/anomalies in images |
| `arduino:vibration_anomaly_detection` | `arduino.app_bricks.vibration_anomaly_detection` | `VibrationAnomalyDetection` | Detect anomalies in vibration data |
| `arduino:gesture_recognition` | `arduino.app_bricks.gesture_recognition` | `GestureRecognition` | Recognize hand gestures |
| `arduino:motion_detection` | `arduino.app_bricks.motion_detection` | `MotionDetection` | Detect/interpret motion (IMU) |
| `arduino:mood_detector` | `arduino.app_bricks.mood_detector` | `MoodDetector` | Detect mood/expression |
| `arduino:audio_classification` | `arduino.app_bricks.audio_classification` | `AudioClassification` | Classify audio (e.g. glass breaking) |
| `arduino:keyword_spotting` | `arduino.app_bricks.keyword_spotting` | `KeywordSpotting` | Spot wake words / keywords ("hey_arduino") |
| `arduino:asr` | `arduino.app_bricks.asr` | `AutomaticSpeechRecognition` | Speech-to-text |
| `arduino:tts` | `arduino.app_bricks.tts` | `TextToSpeech` | Text-to-speech |
| `arduino:sound_generator` | `arduino.app_bricks.sound_generator` | `SoundGenerator`, `MusicComposition`, `SoundEffect` | Generate audio/alarms/music |
| `arduino:wave_generator` | `arduino.app_bricks.wave_generator` | `WaveGenerator` | Generate waveforms |
| `arduino:llm` | `arduino.app_bricks.llm` | `LargeLanguageModel` | Local (on-device) LLM. **In this project** the stock brick isn't installed; a vendored copy lives at `arduino/bricks/personal_llm/` with id `personal:llm`, imported as `from personal_llm import LargeLanguageModel`. |
| `arduino:cloud_llm` | `arduino.app_bricks.cloud_llm` | `CloudLLM`, `CloudModel` | Cloud-hosted LLM (e.g. Gemini) |
| `arduino:vlm` | `arduino.app_bricks.vlm` | `VisionLanguageModel` | Vision-language model (image+text) |
| `arduino:weather_forecast` | `arduino.app_bricks.weather_forecast` | `WeatherForecast` | Weather API (`get_forecast_by_city`) |
| `arduino:telegram_bot` | `arduino.app_bricks.telegram_bot` | `TelegramBot`, `Sender`, `Message` | Telegram bot interface |
| `arduino:arduino_cloud` | `arduino.app_bricks.arduino_cloud` | `ArduinoCloud` | Arduino IoT Cloud integration |
| `arduino:dbstorage_tsstore` | `arduino.app_bricks.dbstorage_tsstore` | `TimeSeriesStore` | Time-series DB storage |
| `arduino:dbstorage_sqlstore` | `arduino.app_bricks.dbstorage_sqlstore` | `SQLStore` | SQL DB storage |

> **Custom Bricks** are supported as of App Lab 0.7 — you can build your own.

## Common API patterns (from real examples)

### Web UI — server + browser messaging
```python
from arduino.app_bricks.web_ui import WebUI
ui = WebUI()
ui.on_message("detect_objects", on_detect_objects)   # browser → Python callback
ui.send_message("detection_result", payload)         # Python → browser
```
Web UI Brick serves the App's `assets/` folder (HTML/JS/CSS). The JS talks to
the Brick (examples bundle `socket.io`).

### Detection Bricks — callbacks per class / for all
```python
from arduino.app_bricks.video_objectdetection import VideoObjectDetection
stream = VideoObjectDetection(confidence=0.5, debounce_sec=0.0)
stream.on_detect("face", face_detected)        # callback for a specific label
stream.on_detect_all(handle_all_detections)    # callback with full dict
stream.override_threshold(0.7)                 # adjust confidence at runtime
```
Still-image object detection:
```python
od = ObjectDetection()
results = od.detect(pil_image, confidence=0.5)
img = od.draw_bounding_boxes(pil_image, results)
# results["detection"] -> list of detections
```

### Keyword spotting → Bridge to MCU
```python
spotter = KeywordSpotting()
spotter.on_detect("hey_arduino", lambda: Bridge.call("keyword_detected"))
```

### Cloud LLM (streaming + memory)
```python
llm = CloudLLM(model=CloudModel.GOOGLE_GEMINI, system_prompt=prompt)
llm.with_memory(20)                  # keep last 20 turns
for chunk in llm.chat_stream(text): ui.send_message("response", chunk)
llm.stop_stream(); llm.clear_memory()
```

### Weather forecast
```python
forecaster = WeatherForecast()
fc = forecaster.get_forecast_by_city("London")
fc.description   # human-readable
fc.category      # category string
```

## Example apps in the official repo (good starting points)
`blink`, `blink-with-ui`, `cloud-blink`, `unoq-pin-toggle`, `color-your-leds`,
`led-matrix-painter`, `real-time-accelerometer`, `object-detection`,
`video-face-detection`, `video-person-classification`,
`video-generic-object-detection`, `mobile-video-generic-object-detection`,
`image-classification`, `code-detector`, `gesture-booth`, `object-hunting`,
`anomaly-detection`, `vibration-anomaly-detection`, `audio-classification`,
`keyword-spotting`, `edge-ai-assistant`, `edge-speech-assistant`,
`edge-dictation-assistant`, `chatbot-cloud-llm`, `bedtime-story-teller`,
`smart-mirror`, `music-composer`, `theremin`, `telegram-bot`, `weather-forecast`,
`air-quality-monitoring`, `home-climate-monitoring-and-storage`,
`system-resources-logger`, `mascot-jump-game`.

Repo: https://github.com/arduino/app-bricks-examples
