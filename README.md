# humex

**Hu**man-**U**nderstandable **ME**trics for everything (**X**).

A vendor-neutral library for turning AV / robotics trajectory data into a
common scenario format and computing behavioral metrics over it. Datasets,
simulators, and metric definitions are all pluggable.

> **Status: beta.** humex is currently being tested internally; a public
> release is planned but not yet out, and the package is not on PyPI
> yet. For now the only install path is from source.

[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-beta-yellow.svg)](#status)

---

## Install (from source)

```bash
git clone https://github.com/zerothlaw-ai/humex.git
cd humex

uv sync                          # if you have uv
# — or —
pip install -e ./humex \
            -e ./converters/waymo \
            -e ./converters/droid \
            -e ./converters/lafan
```

## Quickstart

```bash
humex convert path/to/scenario.tfrecord -o ./converted/
humex plugins
humex evaluate ./converted/scenario1 --metric path/to/metric.yaml
```

## Architecture

```
raw data ─► [converter] ─► scenario.pb + map.pb ─► [hmap] ─► lane_map.pb + role.pb
                                                                    │
                                                                    ▼
                                                              [metric DAG] ─► metric_result.pb
```

- **converters** — Waymo, DROID-100, LAFAN1 as separate plugin packages
  under `converters/`. Add your own by subclassing `BaseConverter`.
- **hmap** — HD-map subsystem.
- **metrics** — DAG composition over `MonitorBase`.
- **proto** — vendor-neutral protobuf schemas.

More detail (Python API, plugin contract, repo layout) is in
[`README-full.md`](README-full.md).

## License

Apache License, Version 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
