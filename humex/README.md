# humex (core)

**Hu**man-**U**nderstandable **ME**trics for everything (**X**) — behavioral
metrics for autonomous-vehicle and physical-AI scenarios.

This is the core `humex` package — `ScenarioAPI`, `HMap`, metric DAGs,
monitors, and the CLI. **Converters ship as separate packages** so heavy
deps (TensorFlow for Waymo, pyarrow/pandas for DROID, …) don't get
pulled into a clean `humex` install.

```bash
pip install humex                          # core only
pip install humex[all]                     # core + all bundled converters
pip install humex humex-converter-waymo    # core + just Waymo
```

See the [workspace README](../README.md) for the full picture.
