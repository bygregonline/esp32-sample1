# Shared TensorFlow Lite Micro demo component

This ESP-IDF component embeds TensorFlow Lite Micro's published float32 Hello World sine model and exposes a small C ABI through `include/ml_demo.h`. The C firmware and Rust firmware call the same initialization and inference functions and use the same model array. It exercises float32 inference on the classic ESP32 CPU/FPU; the ESP32 has no TPU, so this is not a TPU test or performance benchmark.

The model takes one `float32` input in `0..2π` and approximates `sin(x)`. The firmware normalizes temperature, humidity, or fallback battery voltage before each inference. This is a runtime integration demo, not an environmental prediction model.

ESP-IDF Component Manager resolves `espressif/esp-tflite-micro` from `idf_component.yml` when configuring a build.
