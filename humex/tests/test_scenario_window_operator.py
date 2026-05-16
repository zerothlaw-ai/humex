"""Tests for ScenarioWindowOperator."""

import pytest

from humex.metrics.metric_trace import MetricTrace
from humex.metrics.operators.scenario_window import ScenarioWindowOperator
from humex.metrics.operators import ScenarioWindowOperator as ScenarioWindowOperatorFromInit, scenario_window
from humex.metrics.dag.dag_evaluator import OPERATOR_MAPPING
from humex.api.metrics_api.operator_discovery_api import OperatorDiscoveryAPI


class TestScenarioWindowBasic:
    """Single window — values inside pass through, values outside become None."""

    def test_values_inside_window_pass_through(self):
        # Timestamps: 0s, 1s, 2s, 3s, 4s (in nanoseconds)
        ts = [0, int(1e9), int(2e9), int(3e9), int(4e9)]
        trace = MetricTrace(ts, frame_values=[10, 20, 30, 40, 50])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[[1.0, 3.0]])
        assert result.frame_values == [None, 20, 30, 40, None]

    def test_all_inside_window(self):
        ts = [int(1e9), int(2e9), int(3e9)]
        trace = MetricTrace(ts, frame_values=[10, 20, 30])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[[0.0, 5.0]])
        assert result.frame_values == [10, 20, 30]

    def test_all_outside_window(self):
        ts = [int(10e9), int(11e9), int(12e9)]
        trace = MetricTrace(ts, frame_values=[10, 20, 30])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[[0.0, 5.0]])
        assert result.frame_values == [None, None, None]


class TestScenarioWindowMultiple:
    """Multiple windows."""

    def test_two_windows(self):
        # 0s, 1s, 2s, ..., 6s
        ts = [int(i * 1e9) for i in range(7)]
        trace = MetricTrace(ts, frame_values=[0, 1, 2, 3, 4, 5, 6])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[[0.0, 1.0], [4.0, 5.0]])
        assert result.frame_values == [0, 1, None, None, 4, 5, None]

    def test_three_windows(self):
        ts = [int(i * 1e9) for i in range(10)]
        vals = list(range(10))
        trace = MetricTrace(ts, frame_values=vals)
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[[0.0, 1.0], [4.0, 5.0], [8.0, 9.0]])
        expected = [0, 1, None, None, 4, 5, None, None, 8, 9]
        assert result.frame_values == expected


class TestScenarioWindowShorthand:
    """[0.0, 5.0] instead of [[0.0, 5.0]]."""

    def test_single_window_shorthand(self):
        ts = [0, int(1e9), int(2e9), int(3e9)]
        trace = MetricTrace(ts, frame_values=[10, 20, 30, 40])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[0.0, 2.0])
        assert result.frame_values == [10, 20, 30, None]

    def test_shorthand_matches_explicit(self):
        ts = [0, int(1e9), int(2e9)]
        trace = MetricTrace(ts, frame_values=[1, 2, 3])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result_shorthand = op.run(windows=[0.0, 1.0])

        op2 = ScenarioWindowOperator(trace, 'scenario_window')
        result_explicit = op2.run(windows=[[0.0, 1.0]])

        assert result_shorthand.frame_values == result_explicit.frame_values


class TestScenarioWindowEdgeCases:
    """Empty windows (all None), empty trace, boundary-inclusive check."""

    def test_empty_windows_all_none(self):
        ts = [0, int(1e9), int(2e9)]
        trace = MetricTrace(ts, frame_values=[10, 20, 30])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[])
        assert result.frame_values == [None, None, None]

    def test_no_windows_param(self):
        ts = [0, int(1e9)]
        trace = MetricTrace(ts, frame_values=[10, 20])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run()
        assert result.frame_values == [None, None]

    def test_empty_trace(self):
        trace = MetricTrace([], frame_values=[])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[[0.0, 5.0]])
        assert result.frame_values == []

    def test_boundary_inclusive(self):
        # Exactly at window boundaries
        ts = [int(1e9), int(2e9), int(3e9)]
        trace = MetricTrace(ts, frame_values=[10, 20, 30])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[[1.0, 3.0]])
        assert result.frame_values == [10, 20, 30]

    def test_boolean_values(self):
        ts = [0, int(1e9), int(2e9), int(3e9)]
        trace = MetricTrace(ts, frame_values=[True, False, True, False])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[[0.0, 1.0]])
        assert result.frame_values == [True, False, None, None]

    def test_preserves_timestamps(self):
        ts = [0, int(1e9), int(2e9)]
        trace = MetricTrace(ts, frame_values=[10, 20, 30])
        op = ScenarioWindowOperator(trace, 'scenario_window')
        result = op.run(windows=[[0.0, 1.0]])
        assert result.timestamps == ts


class TestScenarioWindowRegistration:
    """In OPERATOR_MAPPING, importable from __init__, discoverable via API."""

    def test_in_operator_mapping(self):
        assert "scenario_window" in OPERATOR_MAPPING
        assert OPERATOR_MAPPING["scenario_window"] is ScenarioWindowOperator

    def test_import_from_init(self):
        assert ScenarioWindowOperatorFromInit is ScenarioWindowOperator

    def test_discovery_api(self):
        api = OperatorDiscoveryAPI()
        info = api.get_operator_info("scenario_window")
        assert info["name"] == "scenario_window"
        assert info["class_name"] == "ScenarioWindowOperator"


class TestScenarioWindowWrapper:
    """Test scenario_window() wrapper function."""

    def test_wrapper_basic(self):
        ts = [0, int(1e9), int(2e9), int(3e9)]
        trace = MetricTrace(ts, frame_values=[10, 20, 30, 40])
        result = scenario_window(trace, windows=[[1.0, 2.0]])
        assert result.frame_values == [None, 20, 30, None]

    def test_wrapper_shorthand(self):
        ts = [0, int(1e9), int(2e9)]
        trace = MetricTrace(ts, frame_values=[10, 20, 30])
        result = scenario_window(trace, windows=[0.0, 1.0])
        assert result.frame_values == [10, 20, None]

    def test_wrapper_multiple_windows(self):
        ts = [int(i * 1e9) for i in range(6)]
        trace = MetricTrace(ts, frame_values=[0, 1, 2, 3, 4, 5])
        result = scenario_window(trace, windows=[[0.0, 1.0], [4.0, 5.0]])
        assert result.frame_values == [0, 1, None, None, 4, 5]
