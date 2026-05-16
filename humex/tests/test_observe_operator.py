"""Tests for ObserveOperator."""

import pytest

from humex.metrics.metric_trace import MetricTrace
from humex.metrics.operators.observe import ObserveOperator
from humex.metrics.operators import ObserveOperator as ObserveOperatorFromInit, observe
from humex.metrics.dag.dag_evaluator import OPERATOR_MAPPING
from humex.api.metrics_api.operator_discovery_api import OperatorDiscoveryAPI


class TestObserveOperatorPassthrough:
    """Verify that ObserveOperator preserves frame_values as-is."""

    def test_numeric_values(self):
        trace = MetricTrace([0, 100, 200], frame_values=[1.5, 2.7, 3.9])
        op = ObserveOperator(trace, 'observe')
        result = op.run()
        assert result.frame_values == [1.5, 2.7, 3.9]

    def test_boolean_values(self):
        trace = MetricTrace([0, 100, 200], frame_values=[True, False, True])
        op = ObserveOperator(trace, 'observe')
        result = op.run()
        assert result.frame_values == [True, False, True]

    def test_none_values(self):
        trace = MetricTrace([0, 100, 200], frame_values=[None, None, None])
        op = ObserveOperator(trace, 'observe')
        result = op.run()
        assert result.frame_values == [None, None, None]

    def test_mixed_values(self):
        trace = MetricTrace([0, 100, 200], frame_values=[1.0, None, 3.0])
        op = ObserveOperator(trace, 'observe')
        result = op.run()
        assert result.frame_values == [1.0, None, 3.0]

    def test_empty_frame_values(self):
        trace = MetricTrace([], frame_values=[])
        op = ObserveOperator(trace, 'observe')
        result = op.run()
        assert result.frame_values == []


class TestObserveOperatorNoVerdict:
    """Verify that ObserveOperator produces no verdict."""

    def test_reduced_result_is_none(self):
        trace = MetricTrace([0, 100], frame_values=[1.0, 2.0])
        result = ObserveOperator(trace, 'observe').run()
        assert result.reduced_result is None

    def test_reduced_value_is_none(self):
        trace = MetricTrace([0, 100], frame_values=[1.0, 2.0])
        result = ObserveOperator(trace, 'observe').run()
        assert result.reduced_value is None

    def test_frame_results_is_empty(self):
        trace = MetricTrace([0, 100], frame_values=[1.0, 2.0])
        result = ObserveOperator(trace, 'observe').run()
        assert result.frame_results == []


class TestObserveOperatorMetadata:
    """Verify that metadata is preserved."""

    def test_segments_preserved(self):
        trace = MetricTrace(
            [0, 100, 200],
            frame_values=[1.0, 2.0, 3.0],
            segments=[(0, 200)]
        )
        result = ObserveOperator(trace, 'observe').run()
        assert result.segments == [(0, 200)]

    def test_source_monitors_preserved(self):
        trace = MetricTrace(
            [0, 100],
            frame_values=[1.0, 2.0],
            source_monitors=[42]
        )
        result = ObserveOperator(trace, 'observe').run()
        assert result.source_monitors == [42]

    def test_timestamps_preserved(self):
        trace = MetricTrace([10, 20, 30], frame_values=[1.0, 2.0, 3.0])
        result = ObserveOperator(trace, 'observe').run()
        assert result.timestamps == [10, 20, 30]


class TestObserveOperatorRegistration:
    """Verify registration in OPERATOR_MAPPING and discovery API."""

    def test_registered_in_operator_mapping(self):
        assert "observe" in OPERATOR_MAPPING
        assert OPERATOR_MAPPING["observe"] is ObserveOperator

    def test_discoverable_via_api(self):
        api = OperatorDiscoveryAPI()
        info = api.get_operators_info()
        names = [op["name"] for op in info["operators"]]
        assert "observe" in names

    def test_discoverable_single_operator(self):
        api = OperatorDiscoveryAPI()
        info = api.get_operator_info("observe")
        assert info["name"] == "observe"
        assert info["class_name"] == "ObserveOperator"
        assert info["parameters"] == []

    def test_validate_operator_call_no_params(self):
        api = OperatorDiscoveryAPI()
        assert api.validate_operator_call("observe") is True


class TestObserveWrapperFunction:
    """Verify the observe() wrapper function."""

    def test_wrapper_returns_metric_trace(self):
        trace = MetricTrace([0, 100], frame_values=[5.0, 10.0])
        result = observe(trace)
        assert isinstance(result, MetricTrace)
        assert result.frame_values == [5.0, 10.0]
        assert result.reduced_result is None
        assert result.reduced_value is None
        assert result.frame_results == []

    def test_import_from_init(self):
        assert ObserveOperatorFromInit is ObserveOperator
