# Rust / ESP-IDF

The Rust implementation targets a dual-USB-C ESP32-S3 N16R8 development board using the Espressif Xtensa toolchain and `esp-idf-svc` with `std`. GPIO assignments follow the ESP32-S3-DevKitC-1 reference; verify the printed pin labels on the purchased carrier board. It serves the auto-refreshing web dashboard/API and a NimBLE GATT service with JSON, text, YAML, and XML snapshots. Its pin assignments are in `rust/src/main.rs`; its register-level BMP280 driver uses I²C1 on GPIO1/2.

```sh
cd rust
./scripts/install-deps.sh
./scripts/build.sh
```

Run `./scripts/build_docs.sh --rust-api` from the repository root to generate Rust source documentation with `cargo doc`. The ESP toolchain and environment are required for this optional API build.

See the [Rust README](https://github.com/bygregonline/esp32-sample1/blob/master/rust/README.md) for deployment details.
