"""Utilities for protobuf text format conversion."""

from google.protobuf import text_format
from google.protobuf.message import Message


def proto_to_text(proto_obj: Message) -> str:
    """Convert a protobuf message object to human-readable text format.

    Args:
        proto_obj: A parsed protobuf message instance.

    Returns:
        Text representation of the protobuf message.
    """
    return text_format.MessageToString(proto_obj)


def proto_from_file(file_path: str, proto_class: type) -> Message:
    """Read a binary .pb file and parse it into a protobuf message.

    Args:
        file_path: Path to the binary .pb file.
        proto_class: The protobuf message class to parse into.

    Returns:
        Parsed protobuf message instance.
    """
    msg = proto_class()
    with open(file_path, "rb") as f:
        msg.ParseFromString(f.read())
    return msg
