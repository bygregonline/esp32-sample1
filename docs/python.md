# MicroPython

The MicroPython version includes the display drivers and GPS parser in the repository. Host-side development tools are installed through `uv`; the board runs standard MicroPython modules.

```sh
cd python
./scripts/install-deps.sh
./scripts/build.sh
./scripts/deploy.sh
```

The MkDocs [Python source reference](reference/python.md) is generated from module docstrings and signatures by `mkdocstrings-python` without importing ESP32-only hardware modules.

See the [MicroPython README](https://github.com/bygregonline/esp32-sample1/blob/master/python/README.md) for wiring and calibration.
