#!/usr/bin/env python3
"""Generate protobuf Python files from .proto sources in proto/.

Outputs to src/humex/proto/. Run via ``make generate``.
"""

import subprocess
import sys
import importlib.util
from pathlib import Path


def run_command(cmd, description):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAIL {description}:")
        print(result.stderr)
        sys.exit(1)
    if result.stdout:
        print(result.stdout)
    print(f"OK {description}")
    return True


def main():
    root_dir = Path(__file__).parent.parent
    proto_dir = root_dir / "proto"
    output_dir = root_dir / "src" / "humex" / "proto"

    proto_files = list(proto_dir.glob("*.proto"))
    if not proto_files:
        print("No .proto files found in proto/")
        sys.exit(1)

    print(f"Found {len(proto_files)} proto files")

    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={output_dir}",
    ] + [str(f) for f in proto_files]
    run_command(cmd, "Proto generation")

    print("\nApplying compatibility fixes...")
    fix_script = root_dir / "scripts" / "fix_pb2_compatibility.py"
    spec = importlib.util.spec_from_file_location("fix_pb2_compatibility", fix_script)
    fix_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fix_module)

    for pb2_file in output_dir.glob("*_pb2.py"):
        fix_module.fix_pb2_file(pb2_file)
    print("OK compatibility fixes applied")

    print(f"\nDone. Generated files in: {output_dir}")


if __name__ == "__main__":
    main()
