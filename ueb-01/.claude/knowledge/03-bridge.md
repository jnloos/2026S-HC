# Bridge — MPU ↔ MCU communication

**Bridge** is the mechanism that lets the Linux/Python side and the MCU/sketch
side exchange data. It uses **Remote Procedure Call (RPC)** with a
**provide / call** pattern: one side *provides* a named function, the other
*calls* it.

## Python side (Linux)
```python
from arduino.app_utils import App, Bridge

# Call a function the sketch has provided:
Bridge.call("set_led_state", led_state)

# Provide a function the sketch can call:
def get_weather_forecast(city: str) -> str:
    ...
    return result
Bridge.provide("get_weather_forecast", get_weather_forecast)

App.run()
```

## Sketch side (MCU, C++)
```cpp
#include "Arduino_RouterBridge.h"

void set_led_state(bool state);

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    Bridge.begin();
    Bridge.provide("set_led_state", set_led_state);   // sketch provides
}

void loop() {
}

void set_led_state(bool state) {
    digitalWrite(LED_BUILTIN, state ? LOW : HIGH);     // LOW = LED on
}
```

## Key API
| Where | Call | Meaning |
|-------|------|---------|
| Python | `Bridge.call(name, *args)` | invoke a function provided by the other side |
| Python | `Bridge.provide(name, fn)` | expose `fn` to be called from the other side |
| Sketch | `Bridge.begin()` | initialize Bridge (in `setup()`) |
| Sketch | `Bridge.provide(name, fn)` | expose a C++ function |
| Sketch | `Bridge.call(name, ...)` | call a Python-provided function |

- Python import: `from arduino.app_utils import Bridge`
- Sketch import: `#include "Arduino_RouterBridge.h"`
- Functions provided via Bridge stay available only while the App runs — which
  is why `App.run()` must keep the App alive.

## Blink example (the canonical end-to-end demo)
Python toggles `led_state` once per second and `Bridge.call("set_led_state", …)`;
the sketch `provide`s `set_led_state` and drives `LED_BUILTIN`. This is the
minimal template for "Linux decides, MCU acts."
