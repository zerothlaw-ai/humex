"""Unit tests for WithinOperator.

Tests cover:
- Basic transition within time budget
- Transition exceeding time budget
- Target never reached
- Multiple null-separated groups
- Different starting conditions
- Edge cases: single-frame group, all null, empty trace
"""

import pytest
from humex.metrics.metric_trace import MetricTrace
from .within import WithinOperator


def _ns(seconds: float) -> int:
    """Convert seconds to nanoseconds."""
    return int(seconds * 1e9)


class TestWithinOperatorBasic:
    """Test basic WithinOperator functionality."""

    def test_transition_within_time(self):
        """Target reached within time budget -> all non-null frames True."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.1), _ns(0.2), _ns(0.3), _ns(0.4)],
            frame_values=[False, False, True, True, True],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=1.0, starting="not_null")
        assert result.frame_values == [True, True, True, True, True]

    def test_transition_exceeds_time(self):
        """Target reached but after time budget -> all non-null frames False."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.5), _ns(1.0), _ns(1.5), _ns(2.0)],
            frame_values=[False, False, False, False, True],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=1.0, starting="not_null")
        assert result.frame_values == [False, False, False, False, False]

    def test_target_never_reached(self):
        """Target never reached -> all non-null frames False."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.1), _ns(0.2)],
            frame_values=[False, False, False],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=1.0, starting="not_null")
        assert result.frame_values == [False, False, False]

    def test_transition_at_exact_boundary(self):
        """Target reached exactly at time budget -> True (<=)."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(1.0)],
            frame_values=[False, True],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=1.0, starting="not_null")
        assert result.frame_values == [True, True]


class TestWithinOperatorGroups:
    """Test null-separated group handling."""

    def test_multiple_groups_independent(self):
        """Each null-separated group is evaluated independently."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.1), _ns(0.2), _ns(0.3), _ns(0.4), _ns(0.5), _ns(0.6)],
            frame_values=[False, True, None, None, False, False, False],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=0.5, starting="not_null")
        # Group 1: [False, True] -> transition at 0.1s <= 0.5s -> True
        # Group 2: [False, False, False] -> target never reached -> False
        assert result.frame_values == [True, True, None, None, False, False, False]

    def test_null_frames_preserved(self):
        """Null frames always remain None in output."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.1), _ns(0.2)],
            frame_values=[None, None, None],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=1.0)
        assert result.frame_values == [None, None, None]

    def test_mixed_groups_different_results(self):
        """Groups can have different results."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.1), _ns(0.2), _ns(10.0), _ns(10.1), _ns(10.2)],
            frame_values=[False, True, True, None, False, True],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=0.5, starting="not_null")
        # Group 1: [False, True, True] -> 0.1s <= 0.5s -> True
        # Group 2: [False, True] -> 0.1s <= 0.5s -> True
        assert result.frame_values == [True, True, True, None, True, True]


class TestWithinOperatorStartingCondition:
    """Test different starting conditions."""

    def test_starting_false(self):
        """starting='false' waits for first False frame to start clock."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.5), _ns(1.0), _ns(1.2)],
            frame_values=[True, True, False, True],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=0.5, starting="false")
        # Clock starts at idx 2 (first False at 1.0s), target at idx 3 (1.2s)
        # Duration: 0.2s <= 0.5s -> True
        assert result.frame_values == [True, True, True, True]

    def test_starting_true_target_false(self):
        """starting='true' with target=False."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.1), _ns(0.2)],
            frame_values=[True, True, False],
        )
        op = WithinOperator(trace)
        result = op.run(target=False, within=0.5, starting="true")
        # Clock starts at idx 0, target at idx 2: 0.2s <= 0.5s -> True
        assert result.frame_values == [True, True, True]

    def test_starting_false_never_found(self):
        """starting='false' but no False frame -> all False."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.1), _ns(0.2)],
            frame_values=[True, True, True],
        )
        op = WithinOperator(trace)
        result = op.run(target=False, within=1.0, starting="false")
        # No False frame to start clock -> False
        assert result.frame_values == [False, False, False]

    def test_starting_not_null_default(self):
        """Default starting='not_null' starts at first non-null frame."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.1), _ns(0.2)],
            frame_values=[False, False, True],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=0.5)
        # Default starting is not_null, starts at idx 0, target at idx 2: 0.2s
        assert result.frame_values == [True, True, True]


class TestWithinOperatorEdgeCases:
    """Test edge cases."""

    def test_single_frame_group_matches_target(self):
        """Single frame that matches target -> True (0 duration <= any budget)."""
        trace = MetricTrace(
            timestamps=[_ns(0)],
            frame_values=[True],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=1.0, starting="not_null")
        assert result.frame_values == [True]

    def test_single_frame_group_no_match(self):
        """Single frame that doesn't match target -> False."""
        trace = MetricTrace(
            timestamps=[_ns(0)],
            frame_values=[False],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=1.0, starting="not_null")
        assert result.frame_values == [False]

    def test_empty_trace(self):
        """Empty trace returns empty."""
        trace = MetricTrace(
            timestamps=[],
            frame_values=[],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=1.0)
        assert result.frame_values == []

    def test_string_coercion(self):
        """YAML string parameters are properly coerced."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.1)],
            frame_values=[False, True],
        )
        op = WithinOperator(trace)
        result = op.run(target="true", within="1.0", starting="not_null")
        assert result.frame_values == [True, True]

    def test_invalid_starting_raises(self):
        """Invalid starting value raises ValueError."""
        trace = MetricTrace(
            timestamps=[_ns(0)],
            frame_values=[True],
        )
        op = WithinOperator(trace)
        with pytest.raises(ValueError, match="Invalid starting value"):
            op.run(target=True, within=1.0, starting="invalid")

    def test_segment_awareness(self):
        """Operator respects segments - out-of-segment frames become None."""
        trace = MetricTrace(
            timestamps=[_ns(0), _ns(0.1), _ns(0.2), _ns(0.3), _ns(0.4)],
            frame_values=[False, True, True, False, True],
            segments=[(_ns(0), _ns(0.2))],
        )
        op = WithinOperator(trace)
        result = op.run(target=True, within=1.0, starting="not_null")
        # Only frames 0-2 are in segment; frames 3-4 are None
        # Group: [False, True, True] -> transition at 0.1s -> True
        assert result.frame_values == [True, True, True, None, None]
