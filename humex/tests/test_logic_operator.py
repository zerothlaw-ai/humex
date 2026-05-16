"""Tests for LogicOperator."""

import pytest

from humex.metrics.metric_trace import MetricTrace
from humex.metrics.operators.logic import LogicOperator
from humex.metrics.operators import LogicOperator as LogicOperatorFromInit, logic
from humex.metrics.dag.dag_evaluator import OPERATOR_MAPPING
from humex.api.metrics_api.operator_discovery_api import OperatorDiscoveryAPI


class TestLogicOperatorAnd:
    """Test AND logic operation."""

    def test_and_all_true(self):
        t1 = MetricTrace([0, 100, 200], frame_values=[True, True, True])
        t2 = MetricTrace([0, 100, 200], frame_values=[True, True, True])
        result = LogicOperator([t1, t2], 'logic').run(op='and')
        assert result.frame_values == [True, True, True]

    def test_and_mixed(self):
        t1 = MetricTrace([0, 100, 200], frame_values=[True, True, False])
        t2 = MetricTrace([0, 100, 200], frame_values=[True, False, True])
        result = LogicOperator([t1, t2], 'logic').run(op='and')
        assert result.frame_values == [True, False, False]

    def test_and_all_false(self):
        t1 = MetricTrace([0, 100], frame_values=[False, False])
        t2 = MetricTrace([0, 100], frame_values=[False, False])
        result = LogicOperator([t1, t2], 'logic').run(op='and')
        assert result.frame_values == [False, False]


class TestLogicOperatorOr:
    """Test OR logic operation."""

    def test_or_mixed(self):
        t1 = MetricTrace([0, 100, 200], frame_values=[True, False, False])
        t2 = MetricTrace([0, 100, 200], frame_values=[False, False, True])
        result = LogicOperator([t1, t2], 'logic').run(op='or')
        assert result.frame_values == [True, False, True]

    def test_or_all_false(self):
        t1 = MetricTrace([0, 100], frame_values=[False, False])
        t2 = MetricTrace([0, 100], frame_values=[False, False])
        result = LogicOperator([t1, t2], 'logic').run(op='or')
        assert result.frame_values == [False, False]


class TestLogicOperatorNonePropagation:
    """Test None propagation behavior."""

    def test_none_in_any_input(self):
        t1 = MetricTrace([0, 100, 200], frame_values=[True, None, False])
        t2 = MetricTrace([0, 100, 200], frame_values=[True, True, None])
        result = LogicOperator([t1, t2], 'logic').run(op='and')
        assert result.frame_values == [True, None, None]

    def test_none_propagation_or(self):
        t1 = MetricTrace([0, 100], frame_values=[None, True])
        t2 = MetricTrace([0, 100], frame_values=[True, None])
        result = LogicOperator([t1, t2], 'logic').run(op='or')
        assert result.frame_values == [None, None]


class TestLogicOperatorMultipleInputs:
    """Test with more than 2 input traces."""

    def test_and_three_inputs(self):
        t1 = MetricTrace([0, 100], frame_values=[True, True])
        t2 = MetricTrace([0, 100], frame_values=[True, True])
        t3 = MetricTrace([0, 100], frame_values=[True, False])
        result = LogicOperator([t1, t2, t3], 'logic').run(op='and', num_inputs=3)
        assert result.frame_values == [True, False]

    def test_or_three_inputs(self):
        t1 = MetricTrace([0, 100], frame_values=[False, False])
        t2 = MetricTrace([0, 100], frame_values=[False, False])
        t3 = MetricTrace([0, 100], frame_values=[False, True])
        result = LogicOperator([t1, t2, t3], 'logic').run(op='or', num_inputs=3)
        assert result.frame_values == [False, True]


class TestLogicOperatorEmptyTraces:
    """Test with empty traces."""

    def test_empty_frame_values(self):
        t1 = MetricTrace([], frame_values=[])
        t2 = MetricTrace([], frame_values=[])
        result = LogicOperator([t1, t2], 'logic').run(op='and')
        assert result.frame_values == []


class TestLogicOperatorInvalidOp:
    """Test invalid operation raises error."""

    def test_unknown_op(self):
        t1 = MetricTrace([0], frame_values=[True])
        t2 = MetricTrace([0], frame_values=[True])
        with pytest.raises(ValueError, match="Unknown logic op"):
            LogicOperator([t1, t2], 'logic').run(op='invalid')

    def test_xor_rejected(self):
        t1 = MetricTrace([0], frame_values=[True])
        t2 = MetricTrace([0], frame_values=[True])
        with pytest.raises(ValueError, match="Unknown logic op"):
            LogicOperator([t1, t2], 'logic').run(op='xor')

    def test_nand_rejected(self):
        t1 = MetricTrace([0], frame_values=[True])
        t2 = MetricTrace([0], frame_values=[True])
        with pytest.raises(ValueError, match="Unknown logic op"):
            LogicOperator([t1, t2], 'logic').run(op='nand')

    def test_nor_rejected(self):
        t1 = MetricTrace([0], frame_values=[True])
        t2 = MetricTrace([0], frame_values=[True])
        with pytest.raises(ValueError, match="Unknown logic op"):
            LogicOperator([t1, t2], 'logic').run(op='nor')


class TestLogicOperatorNumInputs:
    """Test num_inputs validation."""

    def test_default_num_inputs_matches_two(self):
        t1 = MetricTrace([0, 100], frame_values=[True, False])
        t2 = MetricTrace([0, 100], frame_values=[False, True])
        result = LogicOperator([t1, t2], 'logic').run(op='or')
        assert result.frame_values == [True, True]

    def test_num_inputs_three(self):
        t1 = MetricTrace([0, 100], frame_values=[True, False])
        t2 = MetricTrace([0, 100], frame_values=[False, True])
        t3 = MetricTrace([0, 100], frame_values=[True, True])
        result = LogicOperator([t1, t2, t3], 'logic').run(op='and', num_inputs=3)
        assert result.frame_values == [False, False]

    def test_num_inputs_mismatch_too_few(self):
        t1 = MetricTrace([0], frame_values=[True])
        t2 = MetricTrace([0], frame_values=[True])
        with pytest.raises(ValueError, match="Expected 3 input traces, got 2"):
            LogicOperator([t1, t2], 'logic').run(op='and', num_inputs=3)

    def test_num_inputs_mismatch_too_many(self):
        t1 = MetricTrace([0], frame_values=[True])
        t2 = MetricTrace([0], frame_values=[True])
        t3 = MetricTrace([0], frame_values=[True])
        with pytest.raises(ValueError, match="Expected 2 input traces, got 3"):
            LogicOperator([t1, t2, t3], 'logic').run(op='and', num_inputs=2)


class TestLogicWrapperFunction:
    """Test the logic() wrapper function."""

    def test_wrapper_and(self):
        t1 = MetricTrace([0, 100], frame_values=[True, False])
        t2 = MetricTrace([0, 100], frame_values=[True, True])
        result = logic([t1, t2], op='and')
        assert result.frame_values == [True, False]

    def test_wrapper_or(self):
        t1 = MetricTrace([0, 100], frame_values=[True, False])
        t2 = MetricTrace([0, 100], frame_values=[False, False])
        result = logic([t1, t2], op='or')
        assert result.frame_values == [True, False]

    def test_wrapper_num_inputs(self):
        t1 = MetricTrace([0], frame_values=[True])
        t2 = MetricTrace([0], frame_values=[True])
        t3 = MetricTrace([0], frame_values=[False])
        result = logic([t1, t2, t3], op='and', num_inputs=3)
        assert result.frame_values == [False]


class TestLogicRegistration:
    """Test operator registration and discovery."""

    def test_in_operator_mapping(self):
        assert "logic" in OPERATOR_MAPPING
        assert OPERATOR_MAPPING["logic"] is LogicOperator

    def test_import_from_init(self):
        assert LogicOperatorFromInit is LogicOperator

    def test_discovery_api(self):
        api = OperatorDiscoveryAPI()
        info = api.get_operator_info("logic")
        assert info["name"] == "logic"
        assert info["class_name"] == "LogicOperator"

    def test_discovery_api_enums(self):
        enums = OperatorDiscoveryAPI.KNOWN_ENUMS
        assert "logic" in enums
        assert enums["logic"]["op"] == ["and", "or"]
