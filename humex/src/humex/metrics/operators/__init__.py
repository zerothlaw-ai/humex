"""Operator utilities for metric evaluation and data processing.

This module provides both class-based operators and wrapper functions for
metrics evaluation and data transformation. All operators work with MetricTrace
objects to maintain temporal coupling between timestamps and values.

Classes (using verb naming):
    - CompareOperator: Element-wise threshold comparisons
    - ReduceOperator: Time-series reduction to single values
    - AggregateOperator: Time-series aggregation and segmentation
    - TransformOperator: Element-wise mathematical transformations
    - MaskOperator: Frame selection based on boolean conditions
    - DurationOperator: Continuous boolean event duration measurement

Wrapper Functions:
    - compare(): Apply comparison operator to metric trace
    - reduce(): Apply reduction operation to metric trace
    - aggregate(): Apply aggregation operation to metric trace
    - func(): Apply mathematical transformation to metric trace
    - mask(): Apply frame selection mask to metric trace
    - duration(): Measure duration of continuous boolean events

Dictionaries:
    - OPS: Mapping of comparison operator strings to functions
    - FUNCS: Mapping of function names to callable functions
"""

from typing import Any, List, Optional, Union

from humex.metrics.metric_trace import MetricTrace

# Import operator classes
from .compare import CompareOperator, OPS
from .reduce import ReduceOperator
from .aggregate import AggregateOperator
from .transform import TransformOperator, FUNCS
from .mask import MaskOperator
from .observe import ObserveOperator
from .duration import DurationOperator
from .within import WithinOperator
from .logic import LogicOperator
from .arithmetic import ArithmeticOperator
from .scenario_window import ScenarioWindowOperator
from .chain_result import ChainResultOperator


# Backward-compatible wrapper functions

def compare(trace: MetricTrace, op_symbol: str, threshold: Any = None, tolerance_upper: float = 0.0, tolerance_lower: float = 0.0, tolerance: float = 0.0) -> MetricTrace:
    """Apply comparison operator to each element in a metric trace.

    Wrapper for CompareOperator that works with MetricTrace objects.

    Args:
        trace: MetricTrace with values to compare
        op_symbol: Comparison operator as string ('<', '<=', '>', '>=', '==', '!=')
        threshold: Value to compare each element against
        tolerance_upper: Positive tolerance — raises threshold for < / <=, upper bound for == / !=
        tolerance_lower: Negative tolerance — lowers threshold for > / >=, lower bound for == / !=
        tolerance: Deprecated — symmetric tolerance (mapped to upper+lower for backward compat)

    Returns:
        MetricTrace with boolean results of comparison for each element
    """
    operator = CompareOperator(trace, 'compare')
    return operator.run(op_symbol, threshold, tolerance_upper, tolerance_lower, tolerance)


def reduce(trace: MetricTrace, op: str) -> MetricTrace:
    """Apply reduction operation to a metric trace.

    Wrapper for ReduceOperator that works with MetricTrace objects.

    Args:
        trace: MetricTrace with values to reduce (may contain None values)
        op: Reduction operation - 'min', 'max', 'any', 'all', or 'not_any'

    Returns:
        MetricTrace with single element containing the reduced value
    """
    operator = ReduceOperator(trace, 'reduce')
    return operator.run(op)


def aggregate(trace: MetricTrace, op_symbol: str, recalc_segments: bool = False) -> MetricTrace:
    """Apply aggregation operation to a metric trace.

    Wrapper for AggregateOperator that works with MetricTrace objects.

    Args:
        trace: MetricTrace with values to aggregate
        op_symbol: Aggregation operation (currently supports 'continuous_duration')
        recalc_segments: If True, recalculate segments based on output values

    Returns:
        MetricTrace with aggregated values
    """
    operator = AggregateOperator(trace, 'aggregate')
    return operator.run(op_symbol, recalc_segments)


def func(trace: MetricTrace, sign: str) -> MetricTrace:
    """Apply an element-wise math transform to a metric trace.

    Wrapper for TransformOperator that works with MetricTrace objects.

    Args:
        trace: MetricTrace with values to transform
        sign: Name of the function to apply (key in FUNCS)

    Returns:
        MetricTrace with transformed values and None values preserved
    """
    operator = TransformOperator(trace, 'transform')
    return operator.run(sign)


def mask(trace: MetricTrace, mode: str) -> MetricTrace:
    """Apply frame selection mask to a metric trace.

    Wrapper for MaskOperator that works with MetricTrace objects.

    Args:
        trace: MetricTrace with boolean or None values representing frame mask
        mode: Selection mode - 'while' (select frames while True)

    Returns:
        MetricTrace with masked values (None for unselected frames)
    """
    operator = MaskOperator(trace, 'mask')
    return operator.run(mode)


def observe(trace: MetricTrace) -> MetricTrace:
    """Observe metric trace values without producing a verdict.

    Wrapper for ObserveOperator that works with MetricTrace objects.

    Args:
        trace: MetricTrace with values to observe

    Returns:
        MetricTrace with original values preserved, no boolean evaluation
    """
    operator = ObserveOperator(trace, 'observe')
    return operator.run()


def within(trace: MetricTrace, target: bool = True, within_time: float = 1.0, starting: str = "not_null") -> MetricTrace:
    """Check if a boolean state transition happens within a time budget.

    Wrapper for WithinOperator that works with MetricTrace objects.

    Args:
        trace: MetricTrace with boolean/None values
        target: The target boolean state to reach (default: True)
        within_time: Max allowed transition time in seconds (default: 1.0)
        starting: What triggers the clock - "not_null", "false", or "true" (default: "not_null")

    Returns:
        MetricTrace with boolean values per group
    """
    operator = WithinOperator(trace, 'within')
    return operator.run(target, within_time, starting)


def logic(traces: List[MetricTrace], op: str = 'and', num_inputs: int = 2) -> MetricTrace:
    """Apply frame-by-frame boolean logic across multiple traces.

    Wrapper for LogicOperator that works with MetricTrace objects.

    Args:
        traces: List of MetricTraces with boolean frame_values
        op: Logic operation - 'and' or 'or'
        num_inputs: Expected number of input traces (default: 2)

    Returns:
        MetricTrace with boolean results of the logic operation
    """
    operator = LogicOperator(traces, 'logic')
    return operator.run(op, num_inputs)


def arithmetic(traces: List[MetricTrace], op: str = 'add', num_inputs: int = 2, abs_result: bool = False) -> MetricTrace:
    """Apply frame-by-frame arithmetic across multiple float traces.

    Wrapper for ArithmeticOperator that works with MetricTrace objects.

    Args:
        traces: List of MetricTraces with float frame_values
        op: Arithmetic operation - 'add', 'subtract', 'multiply', or 'divide'
        num_inputs: Expected number of input traces (default: 2)
        abs_result: If True, take absolute value of each frame result (default: False)

    Returns:
        MetricTrace with float results of the arithmetic operation
    """
    operator = ArithmeticOperator(traces, 'arithmetic')
    return operator.run(op, num_inputs, abs_result)


def scenario_window(trace: MetricTrace, windows: List = None) -> MetricTrace:
    """Apply time-based windowing to a trace.

    Wrapper for ScenarioWindowOperator that works with MetricTrace objects.

    Args:
        trace: MetricTrace with values to window
        windows: List of [start_sec, end_sec] pairs in seconds.
                 A single [start, end] is auto-wrapped to [[start, end]].

    Returns:
        MetricTrace with original values inside windows, None outside
    """
    operator = ScenarioWindowOperator(trace, 'scenario_window')
    return operator.run(windows)


def duration(trace: MetricTrace, target: bool = True, min_duration: float = 0.0, gap_tolerance: int = 0) -> MetricTrace:
    """Measure duration of continuous boolean events in a metric trace.

    Wrapper for DurationOperator that works with MetricTrace objects.

    Args:
        trace: MetricTrace with boolean values (typically from a compare operator)
        target: Which boolean value constitutes an "event" (default: True)
        min_duration: Minimum run duration in seconds to qualify (default: 0.0)
        gap_tolerance: Max consecutive non-target frames to bridge (default: 0)

    Returns:
        MetricTrace with float duration values (seconds) for qualifying frames, 0.0 elsewhere
    """
    operator = DurationOperator(trace, 'duration')
    return operator.run(target, min_duration, gap_tolerance)


__all__ = [
    # Classes
    'CompareOperator',
    'ReduceOperator',
    'AggregateOperator',
    'TransformOperator',
    'MaskOperator',
    'ObserveOperator',
    'DurationOperator',
    'WithinOperator',
    'LogicOperator',
    'ArithmeticOperator',
    'ScenarioWindowOperator',
    # Wrapper functions
    'compare',
    'reduce',
    'aggregate',
    'func',
    'mask',
    'observe',
    'duration',
    'within',
    'logic',
    'arithmetic',
    'scenario_window',
    # Dictionaries
    'OPS',
    'FUNCS',
]
