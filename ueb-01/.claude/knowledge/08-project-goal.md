# Project Goal — Digital Signage Prototyp

> **What this project actually is.** The Arduino + FastAPI code in this repo is
> not a generic UNO Q demo — it is a research prototype to compare **three
> architectural variants** of context-aware Digital Signage.

## The product idea

A Digital Signage display (Arduino UNO Q with the Web UI Brick on port 7000)
that picks **which HTML screen to show** based on **context**:

- **Vision context** — who/what is in front of the display (camera + image
  recognition).
- **Weather context** — current weather conditions.

The FastAPI service (`api/`) simulates a **CMS**: it hosts HTML content
organized into **pools** (e.g. a "rainy-day pool", a "kids pool", a
"young-adult pool"). The system picks a pool/screen per context and the
Arduino renders it.

## The three variants under comparison

The whole point of the prototype is to **build all three** and compare them on
quality, latency, bandwidth, privacy, cost, and offline-capability.

### Variant 1 — Edge-only (no external LLM)
- Arduino does **image recognition locally** (on-device AI Brick / model).
- Arduino **picks the screen itself** from the CMS pools.
- CMS only serves HTML — it makes **no decisions**.
- Trade-off: best privacy / latency / cost, weakest selection intelligence.

### Variant 2 — Hybrid (edge vision, cloud LLM selection)
- Arduino does **image recognition locally**.
- Arduino sends only an **abstracted audience/context descriptor** (e.g.
  `{"audience": "young_adult", "weather": "rain"}`) to the CMS.
- CMS uses the **Mistral API** to pick the best screen from the pools.
- Trade-off: image stays on device (privacy preserved), but selection is
  smarter than Variant 1.

### Variant 3 — Cloud-only (Mistral does vision + selection)
- Arduino sends the **raw image** to the CMS.
- CMS uses the **Mistral API** for **both** image recognition **and** screen
  selection from the pools, returns the chosen HTML.
- Trade-off: likely highest selection quality, but worst on privacy, latency,
  bandwidth, and cost.

## How to apply this when working in the repo

- The `arduino/` app and the `api/` service must each support **all three
  modes** — design endpoints / app configuration so the variant can be switched
  (e.g. config flag, separate endpoints).
- The CMS needs at minimum: a **pool model** (pools → screens/HTML), an
  endpoint for **direct pool fetch** (Variant 1), an endpoint that takes a
  **context descriptor** and runs Mistral-based selection (Variant 2), and an
  endpoint that takes an **image** and runs Mistral vision + selection
  (Variant 3).
- Mistral API integration belongs in `api/`, not on the Arduino.
- Weather data is an additional context signal — source not yet decided.

## Related

- [[02-app-lab-and-apps]] — Web UI Brick on port 7000 renders the selected HTML.
- [[05-ai-models]] — on-device vision model used in Variants 1 & 2.
- [[07-api-architecture]] — CMS / FastAPI service that hosts the pools.
