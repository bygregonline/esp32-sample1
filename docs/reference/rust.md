# Rust source reference

The Rust implementation has module-level documentation in `rust/src/` for the display, network, GPS, weather, and shared state modules.

Generate native rustdoc HTML with:

```sh
./scripts/build_docs.sh --rust-api
```

The command builds this MkDocs site and adds rustdoc HTML under `site/api/rust/`. It uses the Xtensa toolchain declared by `rust/rust-toolchain.toml`.

After building with `--rust-api`, <a href="../../api/rust/esp32_monitor_rust/index.html">open the generated Rust API reference</a>.
