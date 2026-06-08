# humex

**Hu**man-**U**nderstandable **ME**trics for everything (**X**).

A vendor-neutral library for turning AV / robotics trajectory data into a
common scenario format and computing behavioral metrics over it. Datasets,
simulators, and metric definitions are all pluggable.

> **Status: beta.** humex is published on PyPI but APIs may still change
> between 0.x releases.

[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-beta-yellow.svg)](#status)

---

## Install

> **Always install humex into an isolated environment**, never your system or
> `base`/anaconda Python. humex pins `protobuf<5`, and installing it alongside
> other tools will silently downgrade shared packages and break them. A
> dedicated venv (or pipx) keeps that pin contained.

### From PyPI (recommended)

```bash
python3 -m venv .venv && source .venv/bin/activate   # isolate first
pip install humex            # core + CLI
pip install "humex[all]"     # core + all converter plugins (waymo, droid, lafan)
```

Or install just the converters you need — each pulls in `humex` automatically:

```bash
pip install humex-converter-waymo
pip install humex-converter-droid
pip install humex-converter-lafan
```

If you only want the `humex` CLI (not a library import), [pipx](https://pipx.pypa.io)
isolates it automatically:

```bash
pipx install humex
```

### From source (development)

```bash
git clone https://github.com/zerothlaw-ai/humex.git
cd humex

uv sync                          # creates .venv and installs all workspace members
# — or, without uv —
python3 -m venv .venv && source .venv/bin/activate
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
