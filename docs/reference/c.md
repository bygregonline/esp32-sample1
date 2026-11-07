# C source reference

The C implementation is split into sensor, display, network, weather, and shared-state modules under `c/main/`. The [C implementation guide](../c.md) covers its build and configuration.

Generate detailed header and function documentation with:

```sh
./scripts/build_docs.sh --c-api
```

The command builds this MkDocs site and adds Doxygen HTML under `site/api/c/`. Doxygen is a separate native tool; it is not installed through `uv`.

After building with `--c-api`, <a href="../../api/c/index.html">open the generated C API reference</a>.
