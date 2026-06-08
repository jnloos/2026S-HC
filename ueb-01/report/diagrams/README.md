# Architecture & flow diagrams

Diagrams explaining the most important parts of the ARDU-DigSig-Prototype.
Each diagram has an editable Mermaid source (`.mmd`) and a rendered `.png`.

| # | File | What it shows |
|---|------|---------------|
| 01 | [`01-system-overview.png`](01-system-overview.png) ([src](01-system-overview.mmd)) | Runtime topology: UNO Q board (Linux MPU + STM32 MCU), the DigSig App and its bricks, the on-device docker sidecar for the LLM (`llamacpp-models-runner:9999`) on the `digsig-prototype_default` network, the FastAPI CMS + Caddy on the laptop, the Claude API, and what runs where + the network links. (Audience inference runs in-process inside the App — see diagram 04.) |
| 02 | [`02-pipeline.png`](02-pipeline.png) ([src](02-pipeline.mmd)) | The strategy-slot pipeline `trigger -> audience -> selector -> sink`, with `main.py` as the composition root that swaps one implementation per slot from env config; the context dict flowing through `Pipeline.run_once`, and how errors degrade via the sink. |
| 03 | [`03-variants.png`](03-variants.png) ([src](03-variants.mmd)) | The three variants (V1 `EdgeSelector` / V2 `HybridSelector` / V3 `CloudSelector`): where selection happens, what data leaves the board, and who decides — `GET /pools/{id}` (local pick) vs `POST /pools/{id}/choose-by-context` vs `POST /pools/{id}/choose-by-img`. |
| 04 | [`04-audience-detection.png`](04-audience-detection.png) ([src](04-audience-detection.mmd)) | On-device audience detection: camera frame -> YuNet -> per-face crop -> ONNX MobileNetV3 (age band + gender) -> aggregate -> `target_group` -> `FaceAudienceClassifier` -> `context["audience"]`. Inference runs **in-process** (`AudiencePipeline`, no sidecar). Shows the 5 age bands, 2 genders, 9 target groups, and that the model is trained off-board on FairFace while inference is 100% on-device. |

## Re-rendering

Renderer used: **[`@mermaid-js/mermaid-cli`](https://github.com/mermaid-js/mermaid-cli)** (`mmdc`),
driving the system Chrome headless. The Chrome path + `--no-sandbox` flags live
in `puppeteer-config.json` (checked in).

Run from this directory (`report/diagrams/`):

```bash
for f in 01-system-overview 02-pipeline 03-variants 04-audience-detection; do
  mmdc -i "$f.mmd" -o "$f.png" -p puppeteer-config.json
done
```

If the configured Chrome is not present, edit `executablePath` in
`puppeteer-config.json` to point at any installed Chrome/Chromium, or remove the
key to let mermaid-cli download its own headless shell
(`npx puppeteer browsers install chrome-headless-shell`).

> Note: `graphviz` (`dot`) is also available on this machine, so the `.mmd`
> sources could be ported to `.dot` if a Graphviz pipeline is ever preferred.
