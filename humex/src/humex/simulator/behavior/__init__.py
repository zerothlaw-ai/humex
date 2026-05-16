"""Behavior handlers for vehicle trajectory generation.

This module provides various behavior implementations for controlling
vehicle movements during simulation.
"""

from .behavior_base import BaseBehavior
from .keyframe import KeyframeBehavior
from .smartkeyframe import SmartKeyframeBehavior

__all__ = ["BaseBehavior", "KeyframeBehavior", "SmartKeyframeBehavior"]
