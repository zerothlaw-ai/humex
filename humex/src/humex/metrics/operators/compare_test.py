"""Unit tests for CompareOperator.

Tests cover:
- Boolean, numeric (int/float), and string comparisons
- All supported operators: <, <=, >, >=, ==, !=
- None value handling and preservation
- Segment-aware processing
- Edge cases and error handling
- Metadata preservation
- Time-series processing with multiple values
"""

import pytest
from humex.metrics.metric_trace import MetricTrace
from .compare import CompareOperator


class TestCompareOperatorNumericComparisons:
    """Test CompareOperator with numeric values."""

    def test_greater_than_true(self):
        """Test greater than operator returns True when value > threshold."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[10, 20]
        )
        op = CompareOperator(trace)
        result = op.run('>', 5)
        assert result.frame_values == [True, True]
        assert result.frame_results == [True, True]

    def test_greater_than_false(self):
        """Test greater than operator returns False when value <= threshold."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[3, 5]
        )
        op = CompareOperator(trace)
        result = op.run('>', 5)
        assert result.frame_values == [False, False]

    def test_greater_equal_boundary(self):
        """Test greater or equal operator at boundary."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[5, 10, 4]
        )
        op = CompareOperator(trace)
        result = op.run('>=', 5)
        assert result.frame_values == [True, True, False]

    def test_less_than(self):
        """Test less than operator."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[1, 5, 10]
        )
        op = CompareOperator(trace)
        result = op.run('<', 5)
        assert result.frame_values == [True, False, False]

    def test_less_equal(self):
        """Test less than or equal operator."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[1, 5, 10]
        )
        op = CompareOperator(trace)
        result = op.run('<=', 5)
        assert result.frame_values == [True, True, False]

    def test_equal_numbers(self):
        """Test equality comparison for numbers."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[5, 10, 5]
        )
        op = CompareOperator(trace)
        result = op.run('==', 5)
        assert result.frame_values == [True, False, True]

    def test_not_equal_numbers(self):
        """Test not equal comparison for numbers."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[5, 10, 5]
        )
        op = CompareOperator(trace)
        result = op.run('!=', 5)
        assert result.frame_values == [False, True, False]


class TestCompareOperatorFloatComparisons:
    """Test CompareOperator with floating point values."""

    def test_float_greater_than(self):
        """Test greater than with float values."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[10.5, 5.2]
        )
        op = CompareOperator(trace)
        result = op.run('>', 7.5)
        assert result.frame_values == [True, False]

    def test_float_equal(self):
        """Test equality with float values."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[10.5, 10.5, 10.6]
        )
        op = CompareOperator(trace)
        result = op.run('==', 10.5)
        assert result.frame_values == [True, True, False]

    def test_negative_numbers(self):
        """Test comparison with negative numbers."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[-10, -5, 0]
        )
        op = CompareOperator(trace)
        result = op.run('>', -7)
        assert result.frame_values == [False, True, True]

    def test_zero_comparison(self):
        """Test comparison with zero."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[-1, 0, 1]
        )
        op = CompareOperator(trace)
        result = op.run('>=', 0)
        assert result.frame_values == [False, True, True]


class TestCompareOperatorBooleanComparisons:
    """Test CompareOperator with boolean values."""

    def test_boolean_equal_true(self):
        """Test equality comparison with True."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[True, True]
        )
        op = CompareOperator(trace)
        result = op.run('==', True)
        assert result.frame_values == [True, True]

    def test_boolean_equal_false(self):
        """Test equality comparison with False."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[True, False]
        )
        op = CompareOperator(trace)
        result = op.run('==', False)
        assert result.frame_values == [False, True]

    def test_boolean_not_equal(self):
        """Test not equal comparison with booleans."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[True, False, True]
        )
        op = CompareOperator(trace)
        result = op.run('!=', True)
        assert result.frame_values == [False, True, False]


class TestCompareOperatorStringComparisons:
    """Test CompareOperator with string values."""

    def test_string_equal(self):
        """Test string equality comparison."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=["hello", "world", "hello"]
        )
        op = CompareOperator(trace)
        result = op.run('==', "hello")
        assert result.frame_values == [True, False, True]

    def test_string_not_equal(self):
        """Test string inequality comparison."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=["apple", "banana"]
        )
        op = CompareOperator(trace)
        result = op.run('!=', "apple")
        assert result.frame_values == [False, True]

    def test_string_case_sensitive(self):
        """Test that string comparison is case-sensitive."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=["Hello", "hello"]
        )
        op = CompareOperator(trace)
        result = op.run('==', "hello")
        assert result.frame_values == [False, True]


class TestCompareOperatorNoneHandling:
    """Test CompareOperator's handling of None values."""

    def test_none_values_preserved(self):
        """Test that None values are preserved in output."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000],
            frame_values=[10, None, 20, None]
        )
        op = CompareOperator(trace)
        result = op.run('>', 15)
        assert result.frame_values == [False, None, True, None]

    def test_all_none_input(self):
        """Test comparison with all None values."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[None, None]
        )
        op = CompareOperator(trace)
        result = op.run('>', 5)
        assert result.frame_values == [None, None]

    def test_mixed_none_and_values(self):
        """Test comparison with mixed None and actual values."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000, 5000],
            frame_values=[None, 5, None, 15, None]
        )
        op = CompareOperator(trace)
        result = op.run('>=', 10)
        assert result.frame_values == [None, False, None, True, None]


class TestCompareOperatorSegmentProcessing:
    """Test CompareOperator's segment-aware processing."""

    def test_values_within_segment(self):
        """Test that values within segment are compared normally."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000],
            frame_values=[10, 20, 30, 40],
            segments=[(1500, 3500)]  # Covers 2000 and 3000
        )
        op = CompareOperator(trace)
        result = op.run('>', 15)
        # Values at 1000 and 4000 are outside segment, should be None
        # Values at 2000 and 3000 are inside segment, should be compared
        assert result.frame_values[0] is None  # 1000 outside
        assert result.frame_values[1] == True  # 2000 inside, 20 > 15
        assert result.frame_values[2] == True  # 3000 inside, 30 > 15
        assert result.frame_values[3] is None  # 4000 outside

    def test_multiple_segments(self):
        """Test comparison with multiple segments."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000, 5000],
            frame_values=[10, 20, 30, 40, 50],
            segments=[(1500, 2500), (3500, 4500)]  # Two segments
        )
        op = CompareOperator(trace)
        result = op.run('>', 25)
        assert result.frame_values[0] is None  # 1000 outside
        assert result.frame_values[1] == False  # 2000 inside, 20 > 25 = False
        assert result.frame_values[2] is None  # 3000 outside
        assert result.frame_values[3] == True  # 4000 inside, 40 > 25 = True
        assert result.frame_values[4] is None  # 5000 outside

    def test_no_segments(self):
        """Test that all values are compared when no segments defined."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[10, 20, 30],
            segments=[]  # No segments
        )
        op = CompareOperator(trace)
        result = op.run('>', 15)
        assert result.frame_values == [False, True, True]


class TestCompareOperatorReducedValue:
    """Test CompareOperator's handling of reduced values."""

    def test_reduced_value_comparison_true(self):
        """Test comparison on reduced_value when result is True."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[10, 20],
            reduced_value=15.0
        )
        op = CompareOperator(trace)
        result = op.run('>', 10.0)
        assert result.reduced_result == True
        assert result.reduced_value == 15.0

    def test_reduced_value_comparison_false(self):
        """Test comparison on reduced_value when result is False."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[10, 20],
            reduced_value=5.0
        )
        op = CompareOperator(trace)
        result = op.run('>', 10.0)
        assert result.reduced_result == False

    def test_reduced_value_none(self):
        """Test that reduced_result is None when reduced_value is None."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[10, 20],
            reduced_value=None
        )
        op = CompareOperator(trace)
        result = op.run('>', 10.0)
        assert result.reduced_result is None

    def test_reduced_value_comparison_type_error(self):
        """Test that reduced_result is None when comparison raises TypeError."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[10, 20],
            reduced_value="string_value"  # Cannot compare string with int
        )
        op = CompareOperator(trace)
        result = op.run('>', 10)  # Trying to compare string > int raises TypeError
        assert result.reduced_result is None  # Should handle gracefully


class TestCompareOperatorMetadataPreservation:
    """Test that CompareOperator preserves trace metadata."""

    def test_timestamps_preserved(self):
        """Test that timestamps are preserved."""
        original_timestamps = [1000, 2000, 3000]
        trace = MetricTrace(
            timestamps=original_timestamps,
            frame_values=[10, 20, 30]
        )
        op = CompareOperator(trace)
        result = op.run('>', 15)
        assert result.timestamps == original_timestamps

    def test_source_monitors_preserved(self):
        """Test that source_monitors are preserved."""
        source_monitors = [1, 2, 3]
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[10, 20],
            source_monitors=source_monitors
        )
        op = CompareOperator(trace)
        result = op.run('>', 15)
        assert result.source_monitors == source_monitors

    def test_segments_preserved(self):
        """Test that segments are preserved."""
        segments = [(1000, 2000), (3000, 4000)]
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000],
            frame_values=[10, 20, 30, 40],
            segments=segments
        )
        op = CompareOperator(trace)
        result = op.run('>', 15)
        assert result.segments == segments


class TestCompareOperatorEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_trace(self):
        """Test comparison on empty trace."""
        trace = MetricTrace(
            timestamps=[],
            frame_values=[]
        )
        op = CompareOperator(trace)
        result = op.run('>', 5)
        assert result.frame_values == []

    def test_single_value(self):
        """Test comparison with single value."""
        trace = MetricTrace(
            timestamps=[1000],
            frame_values=[10]
        )
        op = CompareOperator(trace)
        result = op.run('>=', 10)
        assert result.frame_values == [True]

    def test_type_mismatch_string_vs_number(self):
        """Test that type mismatch is handled gracefully with None."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=["hello", 20]
        )
        op = CompareOperator(trace)
        result = op.run('>', 10)
        # First value is string, can't compare with number, should be None
        assert result.frame_values[0] is None
        # Second value is number, should work
        assert result.frame_values[1] == True

    def test_invalid_operator_symbol(self):
        """Test that invalid operator symbol raises KeyError."""
        trace = MetricTrace(
            timestamps=[1000],
            frame_values=[10]
        )
        op = CompareOperator(trace)
        with pytest.raises(KeyError):
            op.run('??', 5)


class TestCompareOperatorMultipleValues:
    """Test CompareOperator with multiple time-series values."""

    def test_multiple_values_all_pass(self):
        """Test comparison where all values pass."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000, 5000],
            frame_values=[100, 110, 120, 130, 140]
        )
        op = CompareOperator(trace)
        result = op.run('>', 50)
        assert all(v == True for v in result.frame_values)

    def test_multiple_values_all_fail(self):
        """Test comparison where all values fail."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000, 5000],
            frame_values=[10, 20, 30, 40, 50]
        )
        op = CompareOperator(trace)
        result = op.run('>', 100)
        assert all(v == False for v in result.frame_values)

    def test_multiple_values_mixed_results(self):
        """Test comparison with mixed pass/fail results."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000, 5000],
            frame_values=[10, 50, 20, 100, 30]
        )
        op = CompareOperator(trace)
        result = op.run('>', 40)
        expected = [False, True, False, True, False]
        assert result.frame_values == expected

    def test_multiple_values_with_none(self):
        """Test mixed values including None."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000, 5000],
            frame_values=[10, None, 50, None, 100]
        )
        op = CompareOperator(trace)
        result = op.run('>', 30)
        expected = [False, None, True, None, True]
        assert result.frame_values == expected


class TestCompareOperatorTolerance:
    """Test CompareOperator's tolerance parameter."""

    def test_greater_than_with_tolerance(self):
        """Test > with tolerance_lower lowers the effective threshold."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[4.6, 4.4, 5.1]
        )
        op = CompareOperator(trace)
        # threshold=5.0, tolerance_lower=0.5 -> effective threshold = 4.5
        result = op.run('>', 5.0, tolerance_lower=0.5)
        assert result.frame_values == [True, False, True]

    def test_greater_equal_with_tolerance(self):
        """Test >= with tolerance_lower lowers the effective threshold."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[4.5, 4.4, 5.0]
        )
        op = CompareOperator(trace)
        result = op.run('>=', 5.0, tolerance_lower=0.5)
        assert result.frame_values == [True, False, True]

    def test_less_than_with_tolerance(self):
        """Test < with tolerance_upper raises the effective threshold."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[5.4, 5.6, 4.0]
        )
        op = CompareOperator(trace)
        # threshold=5.0, tolerance_upper=0.5 -> effective threshold = 5.5
        result = op.run('<', 5.0, tolerance_upper=0.5)
        assert result.frame_values == [True, False, True]

    def test_less_equal_with_tolerance(self):
        """Test <= with tolerance_upper raises the effective threshold."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[5.5, 5.6, 4.0]
        )
        op = CompareOperator(trace)
        result = op.run('<=', 5.0, tolerance_upper=0.5)
        assert result.frame_values == [True, False, True]

    def test_equal_with_tolerance_range_check(self):
        """Test == with tolerance checks if value is within [threshold-lower, threshold+upper]."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000, 5000],
            frame_values=[4.5, 4.4, 5.0, 5.5, 5.6]
        )
        op = CompareOperator(trace)
        # threshold=5.0, tolerance_upper=0.5, tolerance_lower=0.5 -> range [4.5, 5.5]
        result = op.run('==', 5.0, tolerance_upper=0.5, tolerance_lower=0.5)
        assert result.frame_values == [True, False, True, True, False]

    def test_not_equal_with_tolerance_range_check(self):
        """Test != with tolerance checks if value is outside [threshold-lower, threshold+upper]."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000, 5000],
            frame_values=[4.5, 4.4, 5.0, 5.5, 5.6]
        )
        op = CompareOperator(trace)
        # threshold=5.0, tolerance_upper=0.5, tolerance_lower=0.5 -> outside [4.5, 5.5]
        result = op.run('!=', 5.0, tolerance_upper=0.5, tolerance_lower=0.5)
        assert result.frame_values == [False, True, False, False, True]

    def test_asymmetric_tolerance_equal(self):
        """Test == with asymmetric tolerance: different upper and lower bounds."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000, 5000],
            frame_values=[4.0, 4.5, 5.0, 5.5, 6.5]
        )
        op = CompareOperator(trace)
        # threshold=5.0, tolerance_upper=1.0, tolerance_lower=0.5 -> range [4.5, 6.0]
        result = op.run('==', 5.0, tolerance_upper=1.0, tolerance_lower=0.5)
        assert result.frame_values == [False, True, True, True, False]

    def test_zero_tolerance_no_change(self):
        """Test that tolerance=0 produces same results as no tolerance."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[4, 5, 6]
        )
        op = CompareOperator(trace)
        result_default = op.run('>', 5)
        op2 = CompareOperator(trace)
        result_zero = op2.run('>', 5, tolerance_lower=0.0)
        assert result_default.frame_values == result_zero.frame_values

    def test_boolean_threshold_ignores_tolerance(self):
        """Test that tolerance is ignored when threshold is boolean."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[True, False]
        )
        op = CompareOperator(trace)
        result = op.run('==', True, tolerance_upper=0.5, tolerance_lower=0.5)
        assert result.frame_values == [True, False]

    def test_tolerance_with_reduced_value(self):
        """Test that tolerance applies to reduced_value comparison too."""
        trace = MetricTrace(
            timestamps=[1000, 2000],
            frame_values=[10, 20],
            reduced_value=4.6
        )
        op = CompareOperator(trace)
        # Without tolerance, 4.6 > 5.0 is False
        result_no_tol = op.run('>', 5.0)
        assert result_no_tol.reduced_result == False

        op2 = CompareOperator(trace)
        # With tolerance_lower, effective threshold = 4.5, so 4.6 > 4.5 is True
        result_tol = op2.run('>', 5.0, tolerance_lower=0.5)
        assert result_tol.reduced_result == True

    def test_tolerance_with_none_values(self):
        """Test that None values are still preserved with tolerance."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[4.6, None, 4.4]
        )
        op = CompareOperator(trace)
        result = op.run('>', 5.0, tolerance_lower=0.5)
        assert result.frame_values == [True, None, False]


class TestCompareOperatorIntegration:
    """Integration tests combining multiple features."""

    def test_full_workflow_numeric_with_segments(self):
        """Test realistic workflow with numeric values, segments, and metadata."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000, 4000, 5000],
            frame_values=[5.2, 8.3, 12.1, 15.7, 20.4],
            segments=[(1500, 4500)],
            source_monitors=[1, 2],
            reduced_value=12.34
        )
        op = CompareOperator(trace)
        result = op.run('>=', 10.0)

        # Check frame values (with segment consideration)
        assert result.frame_values[0] is None  # Outside segment
        assert result.frame_values[1] == False  # Inside, 8.3 < 10.0
        assert result.frame_values[2] == True   # Inside, 12.1 >= 10.0
        assert result.frame_values[3] == True   # Inside, 15.7 >= 10.0
        assert result.frame_values[4] is None  # Outside segment

        # Check metadata preservation
        assert result.timestamps == trace.timestamps
        assert result.source_monitors == [1, 2]
        assert result.segments == [(1500, 4500)]

        # Check reduced value
        assert result.reduced_result == True  # 12.34 >= 10.0
        assert result.reduced_value == 12.34

    def test_consistency_frame_values_and_frame_results(self):
        """Test that frame_values and frame_results are consistent."""
        trace = MetricTrace(
            timestamps=[1000, 2000, 3000],
            frame_values=[5, 15, 25]
        )
        op = CompareOperator(trace)
        result = op.run('<=', 20)

        # frame_values and frame_results should be identical
        assert result.frame_values == result.frame_results
        assert result.frame_values == [True, True, False]


if __name__ == "__main__":
    # Run tests with pytest when executed directly
    pytest.main([__file__, "-v"])
