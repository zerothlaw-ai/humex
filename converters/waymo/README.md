# humex-converter-waymo

Waymo Open Dataset converter plugin for [humex](https://github.com/zerothlaw-ai/humex).

```bash
pip install humex humex-converter-waymo
```

Recognizes `*.tfrecord` files (including sharded `*.tfrecord-NNNNN-of-NNNNN`).
Discovered automatically by humex via the `humex.converters` entry point — no
extra registration step. Run:

```bash
humex convert path/to/scenario.tfrecord -o ./converted/
```

## Why a separate package?

The `waymo-open-dataset-tf-2-12-0` dependency pulls in TensorFlow, which
conflicts with humex's numpy pin and would block clean installs for users who
just want to run metrics over already-converted scenarios. Keeping the Waymo
toolchain in its own wheel means a bare `pip install humex` stays small.
