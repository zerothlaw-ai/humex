# humex-converter-droid

DROID-100 (LeRobot / Franka Panda) converter plugin for
[humex](https://github.com/zerothlaw-ai/humex).

```bash
pip install humex humex-converter-droid
```

Recognizes `*.parquet` files that carry DROID-100's column schema
(`observation.state`, `episode_index`). The detection runs a cheap
column-only parquet read, so generic `.parquet` files from other sources
are correctly skipped.

```bash
humex convert path/to/file-000.parquet -o ./converted/                # every episode
humex convert path/to/file-000.parquet -o ./converted/ -O episode=0   # one episode
```

The Franka Panda URDF + meshes ship inside the wheel — no extra download.
