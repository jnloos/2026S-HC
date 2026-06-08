# Arduino UNO Q — Hardware

The **Arduino UNO Q** is a "dual-brain" board in the classic UNO form factor. It
combines a Linux application processor (MPU) with a real-time microcontroller
(MCU) on one board.

## Processors

### MPU — "Linux side"
- **Qualcomm Dragonwing™ QRB2210** System-on-Chip
- Quad-core **Arm Cortex-A53 @ 2.0 GHz**
- Adreno GPU (3D acceleration)
- 2× ISP (13 MP + 13 MP, or 25 MP) @ 30 fps — for camera input
- Runs a **Debian Linux** OS
- Runs Python apps, AI models, web servers, external service calls

### MCU — "Arduino side"
- **STMicroelectronics STM32U585**
- **Arm Cortex-M33 up to 160 MHz**, with FPU
- 2 MB flash, 786 kB SRAM
- Programmed like a classic Arduino (C++ sketch). Toolchain platform is
  `arduino:zephyr` (see `sketch.yaml`).
- Handles real-world I/O: sensors, LEDs, motors, GPIO.

## Memory & storage (board-level)
- **LPDDR4 RAM**: 2 GB or 4 GB variants (4 GB recommended for standalone/SBC use)
- **16 GB eMMC** storage

## Connectivity
- **WCBN3536A** module: **Wi-Fi 5** dual-band (2.4/5 GHz) + **Bluetooth 5.1**,
  onboard antennas
- **USB-C** connector (power + data; also used with a dongle for SBC mode)

## On-board features
- Blue **13×8 LED matrix**
- Classic **UNO pin headers** (shield-compatible)
- **SPI** and **I2C / Qwiic** connectors
- **Qwiic connector** → connect **Modulino** nodes (temperature, LED pixels,
  buttons, distance, etc.) and other Qwiic components
- **High-speed bottom headers** for Arduino carriers, MIPI-CSI cameras, MIPI-DSI
  displays

## ⚠️ Operating voltages (critical)
- **MCU GPIO / analog pins: 3.3 V only.**
- **SoC high-speed bottom headers: 1.8 V only.** Connecting higher-voltage
  components to the high-speed headers **can damage the board**.

## Why the duality matters (typical split)
A single project can:
- Read a sensor value → **MCU side**
- Capture camera input → **Linux side**
- Run an AI model on the camera feed → **Linux side**
- Stream data to a local web server → **Linux side**

Full hardware page: https://docs.arduino.cc/hardware/uno-q/
