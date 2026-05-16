"""Pure Python TFRecord reader.

Reads TFRecord files without requiring TensorFlow. The TFRecord format stores
a sequence of records, each preceded by a length and CRC checksums.

Record format:
    uint64 length
    uint32 masked_crc32_of_length
    byte   data[length]
    uint32 masked_crc32_of_data
"""

import struct
from pathlib import Path


def read_tfrecord(path: str | Path) -> list[bytes]:
    """Read all records from an uncompressed TFRecord file.

    Args:
        path: Path to a .tfrecord file.

    Returns:
        List of raw bytes for each record.
    """
    records = []
    with open(path, "rb") as f:
        while True:
            # Read length (uint64) + CRC of length (uint32) = 12 bytes
            header = f.read(12)
            if len(header) == 0:
                break  # EOF
            if len(header) < 12:
                raise ValueError(f"Truncated record header in {path}")
            length = struct.unpack("<Q", header[:8])[0]
            # Read data + CRC of data (uint32) = length + 4 bytes
            payload = f.read(length + 4)
            if len(payload) < length + 4:
                raise ValueError(f"Truncated record data in {path}")
            records.append(payload[:length])
    return records
