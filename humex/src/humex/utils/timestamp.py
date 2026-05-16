"""Timestamp utilities for Ava framework.

This module provides conversion functions between float seconds and int64 nanoseconds.
All internal timestamps in Ava use int64 nanoseconds for precision and consistency.
"""

from typing import Union

# Nanoseconds per second (SI unit)
NS_PER_SECOND = 1_000_000_000

# Type alias for clarity
Timestamp = Union[int, float]  # int64 ns or float seconds


def to_ns(ts: float) -> int:
    """Convert timestamp from float seconds to int64 nanoseconds.

    Args:
        ts: Timestamp in float seconds (e.g., 0.1 for 100 milliseconds)

    Returns:
        Timestamp in int64 nanoseconds, rounded to nearest nanosecond

    Examples:
        >>> to_ns(0.0)
        0
        >>> to_ns(0.1)
        100000000
        >>> to_ns(1.5)
        1500000000
        >>> to_ns(0.000000001)  # 1 nanosecond
        1
    """
    if ts is None:
        return None
    return int(round(ts * NS_PER_SECOND))


def to_seconds(ts: int) -> float:
    """Convert timestamp from int64 nanoseconds to float seconds.

    Args:
        ts: Timestamp in int64 nanoseconds

    Returns:
        Timestamp in float seconds

    Examples:
        >>> to_seconds(0)
        0.0
        >>> to_seconds(100000000)
        0.1
        >>> to_seconds(1500000000)
        1.5
        >>> to_seconds(1)  # 1 nanosecond
        1e-09
    """
    if ts is None:
        return None
    return ts / NS_PER_SECOND


def validate_timestamp_ns(ts: int) -> bool:
    """Validate that timestamp is a reasonable int64 nanosecond value.

    Args:
        ts: Timestamp in int64 nanoseconds

    Returns:
        True if timestamp is valid (non-negative, within reasonable range)

    Raises:
        ValueError: If timestamp is invalid
    """
    if ts is None:
        return True
    if not isinstance(ts, int):
        raise ValueError(f"Timestamp must be int64, got {type(ts).__name__}")
    if ts < 0:
        raise ValueError(f"Timestamp must be non-negative, got {ts}")
    # Max reasonable timestamp: ~292 years in nanoseconds
    if ts > 9_223_372_035_854_775_807:  # Max int64 - small margin
        raise ValueError(f"Timestamp exceeds int64 range: {ts}")
    return True


def validate_timestamp_seconds(ts: float) -> bool:
    """Validate that timestamp is a reasonable float seconds value.

    Args:
        ts: Timestamp in float seconds

    Returns:
        True if timestamp is valid (non-negative, within reasonable range)

    Raises:
        ValueError: If timestamp is invalid
    """
    if ts is None:
        return True
    if not isinstance(ts, (int, float)):
        raise ValueError(f"Timestamp must be float/int, got {type(ts).__name__}")
    if ts < 0:
        raise ValueError(f"Timestamp must be non-negative, got {ts}")
    # Max reasonable timestamp: ~292 years in seconds
    if ts > 9.223e9:
        raise ValueError(f"Timestamp exceeds reasonable range: {ts}")
    return True
