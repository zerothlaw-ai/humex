# humex-converter-lafan

LAFAN1 (Unitree H1) retargeted motion converter plugin for
[humex](https://github.com/zerothlaw-ai/humex).

```bash
pip install humex humex-converter-lafan
```

Recognizes `.csv` files matching the LAFAN1-H1 schema (26 columns, no
header). Generic CSVs from other sources are correctly skipped via column
sniffing.

```bash
humex convert h1/walk1_subject1.csv -o ./converted/   # one motion
humex convert ../lafan_raw_data/h1/ -o ./converted/   # every motion under h1/
```

The H1 URDF + meshes ship inside the wheel.
