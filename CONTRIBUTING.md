# Contributing to humex

Thanks for your interest! `humex` is an Apache 2.0 library and we welcome pull
requests.

## Quick start

```bash
git clone https://github.com/zerothlaw-ai/humex.git
cd humex
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest tests/
```

## Project layout

```
src/humex/
├── proto/         # vendored protobuf schemas
├── hmap/          # HD-map subsystem (HMap, LaneMap, RoadMap, role_table)
├── converters/    # dataset → scenario.pb (BaseConverter + Waymo/DROID/LAFAN)
├── metrics/       # MonitorBase + DAG evaluator + operator library
├── api/           # high-level Python API surface
├── components/    # core data structures (Scenario, Frame, Object, StatePoint)
├── simulator/     # runtime simulation state types
├── utils/         # helpers
└── cli/           # `humex` command-line entry points
```

## Where to put a change

| Change | Goes in |
|---|---|
| New dataset converter | `src/humex/converters/<dataset>.py` + `<dataset>_scenario_converter.py` |
| New metric monitor | `src/humex/metrics/monitors/catalog/<name>.py` |
| New CLI subcommand | `src/humex/cli/<name>.py` + register in `src/humex/cli/main.py` |
| New proto field | `proto/*.proto` → `make generate` |
| Bug fix in the map / role builder | `src/humex/hmap/` |

Keep files **under 500 lines**. Split logical units rather than letting a file grow.

## Adding a new converter

See [`docs/CONVERTERS.md`](docs/CONVERTERS.md). The contract:

1. Subclass `humex.converters.base.BaseConverter`.
2. Implement `name`, `_check_dependencies`, `convert(output_dir, ...)`, `validate_input`.
3. Output `scenario.pb` + `map.pb` + `meta.json` in `<output_dir>/<scenario_name>/`.
4. Wire detection into `humex.cli.convert` (file extension dispatch).
5. Add 2–3 fixture tests under `tests/test_converters/`.

## Tests

```bash
pytest tests/
pytest tests/test_cli/         # CLI smoke tests
pytest tests/test_converters/  # dataset round-trip tests
```

Tests that need large fixture files (e.g. real TFRecords) should `pytest.skip()`
when the data isn't present, so a clean checkout still produces a green run.

## Code style

- Python 3.11.
- 4-space indentation.
- Type-annotate public APIs.
- Default to no comments; add one only when the **why** is non-obvious.
- Prefer editing existing files over creating new ones.

## Commit messages

Conventional-style summary on the first line, e.g.:

- `hmap: split corridor builder out of role_table_builder`
- `converters: drop legacy DROID v0 schema support`
- `cli: humex evaluate writes metric_result.pb instead of stdout dump`

## Filing issues

When reporting a bug, include:

1. `humex --version`
2. Python version and OS
3. The dataset / scenario you were processing (or a minimal repro)
4. Full traceback
