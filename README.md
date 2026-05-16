# humex

**Behavioral metrics for autonomous-vehicle and physical-AI scenarios.**

`humex` converts raw recorded or simulated trajectory data into a vendor-neutral
scenario protobuf and computes behavioral metrics (front / rear / side neighbors,
lane occupancy, ego-relative roles, custom metric DAGs) over it — dataset- and
simulator-agnostic.

[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)

---

## Install

```bash
pip install humex
```

Or from source:

```bash
git clone https://github.com/zerothlaw-ai/humex.git
cd humex
pip install -e .
```

## Quickstart

```bash
# 1. Convert a raw dataset into a scenario
humex convert path/to/waymo.tfrecord -o ./converted/

# 2. (Optional) Rebuild lane_map + role sidecars
humex lane-map ./converted/<scenario_name>

# 3. Compute a metric DAG over it
humex evaluate ./converted/<scenario_name> --metric configs/front_distance.yaml

# 4. Package as a portable .hpkg
humex package ./converted/<scenario_name>
```

## Architecture

```
recorded / sim data → [converter] → scenario.pb + map.pb → [hmap] → lane_map.pb + role.pb
                                                                          ↓
                                                                   [metric DAG] → metric_result.pb
```

- **converters** — Waymo, DROID, LAFAN1 (Unitree H1) out of the box; write your own by extending `BaseConverter`.
- **hmap** — HD-map subsystem (`HMap` facade + `LaneMap` graph + `RoadMap` raw data).
- **metrics** — DAG-based metric composition over `MonitorBase` building blocks.
- **proto** — vendor-neutral schema: `scenario.proto`, `map.proto`, `lane_map.proto`, `role.proto`.

## Python API

```python
from humex import ScenarioAPI, HMap, LaneMap, RoadMap, build_lane_map, build_role_table
from humex.metrics import MonitorBase

# Load
scenario = ScenarioAPI().load_from_proto_files("converted/segment/scenario.pb")

# Use the map
lane_id = scenario.map.find_closest_lane(position=(10.0, 0.0, 0.0), heading=0.0)
```

## Supported datasets

| Dataset | Format | Status |
|---|---|---|
| Waymo Open Dataset | `.tfrecord` | ✅ |
| DROID-100 (`lerobot/droid_100`) | `.parquet` | ✅ |
| LAFAN1 (retargeted Unitree H1) | `.csv` | ✅ |
| Your dataset | — | [extend `BaseConverter`](docs/CONVERTERS.md) |

## Documentation

- [`docs/CONVERTERS.md`](docs/CONVERTERS.md) — write a new dataset converter
- [`docs/METRICS.md`](docs/METRICS.md) — write a `MonitorBase`, compose into a DAG
- [`docs/ROLES.md`](docs/ROLES.md) — the `role.pb` schema and how monitors consume it

## Optional dependencies

- `humex[waymo]` — adds Waymo Open Dataset TFRecord parsing
- `humex[local]` — adds matplotlib for local plotting helpers

## License

humex is licensed under the [Apache License, Version 2.0](LICENSE) — a
permissive license with an explicit patent grant. In short, you can use,
modify, redistribute, and embed humex (including in commercial products)
provided you keep the copyright notice and the LICENSE file with the code.

See [`NOTICE`](NOTICE) for the copyright statement and a list of vendored
components.

**Dependency licenses.** All runtime dependencies are OSI-approved
permissive licenses (BSD, MIT, Apache 2.0). The HTTPS client `requests`
pulls in `certifi`, which is Mozilla Public License 2.0; humex does not
bundle or modify certifi, so MPL obligations stay with that upstream
package.

**Contributor licensing.** By opening a pull request you agree that your
contribution is licensed under the same Apache 2.0 license as the
project (inbound = outbound — no separate CLA required).

## Contributing

Pull requests welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the
contributor guide and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for
expected conduct.

## Contact

General questions, bug reports, and contributor coordination happen on
[GitHub Issues](https://github.com/zerothlaw-ai/humex/issues). For
anything that doesn't fit there, reach the maintainers at
**humex@zerothlaw.io**.
