#!/usr/bin/env python3
"""Fix protobuf-version compatibility issues in generated pb2 files."""

import re
from pathlib import Path


def fix_pb2_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    content = re.sub(
        r'^from google\.protobuf import runtime_version',
        '# from google.protobuf import runtime_version',
        content,
        flags=re.MULTILINE,
    )

    content = re.sub(
        r'_runtime_version\.ValidateProtobufRuntimeVersion\(\s*\n(.*?\n)*?\)',
        '# ValidateProtobufRuntimeVersion call removed for compatibility',
        content,
    )

    content = re.sub(
        r'^import (\w+_pb2) as (\w+__pb2)',
        r'from . import \1 as \2',
        content,
        flags=re.MULTILINE,
    )

    with open(filepath, 'w') as f:
        f.write(content)

    print(f"Fixed {filepath.name}")


if __name__ == '__main__':
    proto_dir = Path(__file__).parent.parent / 'src' / 'humex' / 'proto'

    for pb2_file in proto_dir.glob('*_pb2.py'):
        fix_pb2_file(pb2_file)

    print("All pb2 files fixed!")
