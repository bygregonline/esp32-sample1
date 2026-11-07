# Rust / ESP-IDF

The Rust implementation uses the Espressif Xtensa toolchain and `esp-idf-svc` with `std`. Its pin assignments are in `rust/src/main.rs`.

```sh
cd rust
./scripts/install-deps.sh
./scripts/build.sh
```

Run `./scripts/build_docs.sh --rust-api` from the repository root to generate Rust source documentation with `cargo doc`. The ESP toolchain and environment are required for this optional API build.

See the [Rust README](https://github.com/bygregonline/esp32-sample1/blob/master/rust/README.md) for deployment details.
