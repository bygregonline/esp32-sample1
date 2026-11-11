# ESP32 Telemetry Monitor

![Telemetry monitor hero](visuals/hero-esp32-telemetry.png)

This documentation covers a telemetry monitor for a dual-USB-C ESP32-S3 N16R8 development board, using the ESP32-S3-DevKitC-1 GPIO map as a reference. Check the printed labels on the purchased carrier board before wiring. The C, MicroPython, and Rust implementations provide sensor readings, Wi-Fi setup, an HTTP API, weather forecasts, and two displays. The Arduino sketch covers sensors and displays.

Start with [hardware and wiring](hardware.md), then choose an implementation:

- [C / ESP-IDF](c.md) — reference firmware.
- [MicroPython](python.md) — firmware copied to the board with `mpremote`.
- [Rust](rust.md) — ESP-IDF `std` firmware for Xtensa.
- [Arduino](arduino.md) — sketch for Arduino IDE or CLI.

The [HTTP API](api.md) is shared by the C, MicroPython, and Rust versions.
