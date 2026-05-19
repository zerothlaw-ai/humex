# humex

**Hu**man-**U**nderstandable **ME**trics for everything (**X**).

A vendor-neutral library for turning AV / robotics trajectory data into a
common scenario format and computing behavioral metrics over it. Datasets,
simulators, and metric definitions are all pluggable.

[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org)

---

## Install

```bash
pip install humex                          # core (small)
pip install humex[all]                     # core + every official converter
pip install humex humex-converter-waymo    # core + just one converter
```

Available converter plugins, each a separate PyPI package:

| Plugin | Recognises | Heavy deps |
|---|---|---|
| `humex-converter-waymo` | `*.tfrecord` (incl. sharded) | waymo-open-dataset, TF |
| `humex-converter-droid` | `*.parquet` (DROID-100) | pandas, pyarrow |
| `humex-converter-lafan` | `*.csv` (LAFAN1 H1) | pandas |

Bare `pip install humex` stays clean — heavy deps live in their plugin
packages, not the core.

## Quickstart

```bash
pip install humex[all]                              # all converters

# 1. Convert a raw dataset → scenario directory + .humex archive
humex convert path/to/scenario.tfrecord -o ./converted/

# 2. See what's installed
humex plugins

# 3. Compute a metric over a converted scenario
humex evaluate ./converted/scenario1 --metric path/to/metric.yaml
```

## Python API

```python
from humex import ScenarioAPI

scenario = ScenarioAPI().load_from_proto_files(
    scenario_file_path="converted/scenario1/scenario.pb",
    map_file_path="converted/scenario1/map.pb",
)

# Map queries
lane_id = scenario.map.find_closest_lane(position=(10.0, 0.0, 0.0), heading=0.0)
```

## Architecture

```
raw data ─► [converter plugin] ─► scenario.pb + map.pb ─► [hmap] ─► lane_map.pb + role.pb
                                                                            │
                                                                            ▼
                                                                    [metric DAG] ─► metric_result.pb
```

- **converters** — separate pip packages registered via the `humex.converters`
  entry-point group. Bundled formats: Waymo, DROID-100, LAFAN1. Write your own
  by subclassing `BaseConverter` and declaring one entry-point line in your
  package's `pyproject.toml` — humex discovers it automatically.
- **hmap** — HD-map subsystem: `HMap` facade, `LaneMap` graph, `RoadMap` raw
  data, `RoleTable` precomputed front/rear neighbours.
- **metrics** — DAG composition over `MonitorBase` primitives; ships with a
  catalogue of common monitors.
- **proto** — vendor-neutral protobuf schemas under `humex/proto/`.

## Writing a converter plugin

A converter is one class + one entry-point line. The full contract is
`humex.converters.base.BaseConverter`. Minimal sketch:

```python
# humex_converter_myformat/converter.py
from pathlib import Path
from humex.converters.base import BaseConverter, ConversionResult

class MyFormatConverter(BaseConverter):
    EXTENSIONS = (".myfmt",)

    @property
    def name(self) -> str:
        return "myformat"

    def convert(self, output_dir=None, **kwargs) -> ConversionResult:
        ...  # write scenario.pb, map.pb, return ConversionResult(...)
```

```toml
# humex_converter_myformat/pyproject.toml
[project]
name = "humex-converter-myformat"
dependencies = ["humex>=0.2,<0.3"]

[project.entry-points."humex.converters"]
myformat = "humex_converter_myformat:MyFormatConverter"
```

`pip install humex humex-converter-myformat` and `humex convert foo.myfmt`
will route to it. There's a reusable contract test at
`humex.converters.testing.ConverterContract` you can subclass in your
plugin's test suite to verify registration + dispatch.

## Repository layout

This repo is a monorepo with one core wheel and one wheel per converter
plugin, managed as a [uv](https://docs.astral.sh/uv/) workspace:

```
humex/                    # the core (published as `humex`)
  src/humex/
  tests/
converters/
  waymo/                  # published as `humex-converter-waymo`
  droid/                  # published as `humex-converter-droid`
  lafan/                  # published as `humex-converter-lafan`
```

Adding a new bundled converter is `mkdir converters/<name>` with its own
`pyproject.toml`; the workspace glob picks it up. See
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Development

```bash
git clone https://github.com/zerothlaw-ai/humex.git
cd humex

# All members of the workspace, editable:
uv sync                                   # if you have uv
# or:
pip install -e ./humex
pip install -e ./converters/waymo
pip install -e ./converters/droid
pip install -e ./converters/lafan

cd humex && pytest tests/
```

## Status

`humex` is **0.2.0 — beta**. Public APIs (`ScenarioAPI`, `HMap`, the
converter plugin contract) follow semver from 0.2 onward; breaking changes
will bump the minor.

## License

Apache License, Version 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
By submitting a pull request you agree your contribution is licensed under
the same terms (inbound = outbound — no separate CLA).

## Contact

[GitHub Issues](https://github.com/zerothlaw-ai/humex/issues) for bugs and
questions. Maintainers: **humex@zerothlaw.io**.
