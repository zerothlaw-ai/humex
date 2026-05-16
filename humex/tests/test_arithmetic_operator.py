"""Tests for ArithmeticOperator."""

import pytest

from humex.metrics.metric_trace import MetricTrace
from humex.metrics.operators.arithmetic import ArithmeticOperator
from humex.metrics.operators import ArithmeticOperator as ArithmeticOperatorFromInit, arithmetic
from humex.metrics.dag.dag_evaluator import OPERATOR_MAPPING
from humex.api.metrics_api.operator_discovery_api import OperatorDiscoveryAPI


class TestArithmeticAdd:
    """Test add operation."""

    def test_add_two_inputs(self):
        t1 = MetricTrace([0, 100, 200], frame_values=[1.0, 2.0, 3.0])
        t2 = MetricTrace([0, 100, 200], frame_values=[4.0, 5.0, 6.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='add')
        assert result.frame_values == [5.0, 7.0, 9.0]

    def test_add_three_inputs(self):
        t1 = MetricTrace([0, 100], frame_values=[1.0, 2.0])
        t2 = MetricTrace([0, 100], frame_values=[3.0, 4.0])
        t3 = MetricTrace([0, 100], frame_values=[5.0, 6.0])
        result = ArithmeticOperator([t1, t2, t3], 'arithmetic').run(op='add', num_inputs=3)
        assert result.frame_values == [9.0, 12.0]

    def test_add_negative_values(self):
        t1 = MetricTrace([0, 100], frame_values=[-1.0, 2.5])
        t2 = MetricTrace([0, 100], frame_values=[3.0, -4.5])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='add')
        assert result.frame_values == [2.0, -2.0]


class TestArithmeticSubtract:
    """Test subtract operation."""

    def test_subtract_two_inputs(self):
        t1 = MetricTrace([0, 100, 200], frame_values=[10.0, 20.0, 30.0])
        t2 = MetricTrace([0, 100, 200], frame_values=[3.0, 5.0, 10.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='subtract')
        assert result.frame_values == [7.0, 15.0, 20.0]

    def test_subtract_three_inputs(self):
        t1 = MetricTrace([0, 100], frame_values=[100.0, 50.0])
        t2 = MetricTrace([0, 100], frame_values=[20.0, 10.0])
        t3 = MetricTrace([0, 100], frame_values=[30.0, 5.0])
        result = ArithmeticOperator([t1, t2, t3], 'arithmetic').run(op='subtract', num_inputs=3)
        assert result.frame_values == [50.0, 35.0]


class TestArithmeticMultiply:
    """Test multiply operation."""

    def test_multiply_two_inputs(self):
        t1 = MetricTrace([0, 100], frame_values=[2.0, 3.0])
        t2 = MetricTrace([0, 100], frame_values=[4.0, 5.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='multiply')
        assert result.frame_values == [8.0, 15.0]

    def test_multiply_by_zero(self):
        t1 = MetricTrace([0, 100], frame_values=[5.0, 10.0])
        t2 = MetricTrace([0, 100], frame_values=[0.0, 2.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='multiply')
        assert result.frame_values == [0.0, 20.0]

    def test_multiply_three_inputs(self):
        t1 = MetricTrace([0], frame_values=[2.0])
        t2 = MetricTrace([0], frame_values=[3.0])
        t3 = MetricTrace([0], frame_values=[4.0])
        result = ArithmeticOperator([t1, t2, t3], 'arithmetic').run(op='multiply', num_inputs=3)
        assert result.frame_values == [24.0]


class TestArithmeticDivide:
    """Test divide operation."""

    def test_divide_two_inputs(self):
        t1 = MetricTrace([0, 100], frame_values=[10.0, 20.0])
        t2 = MetricTrace([0, 100], frame_values=[2.0, 5.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='divide')
        assert result.frame_values == [5.0, 4.0]

    def test_divide_by_zero_returns_none(self):
        t1 = MetricTrace([0, 100, 200], frame_values=[10.0, 20.0, 30.0])
        t2 = MetricTrace([0, 100, 200], frame_values=[2.0, 0.0, 5.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='divide')
        assert result.frame_values == [5.0, None, 6.0]

    def test_divide_three_inputs(self):
        t1 = MetricTrace([0], frame_values=[100.0])
        t2 = MetricTrace([0], frame_values=[2.0])
        t3 = MetricTrace([0], frame_values=[5.0])
        result = ArithmeticOperator([t1, t2, t3], 'arithmetic').run(op='divide', num_inputs=3)
        assert result.frame_values == [10.0]

    def test_divide_by_zero_in_chain(self):
        """Division by zero in second divisor should also return None."""
        t1 = MetricTrace([0], frame_values=[100.0])
        t2 = MetricTrace([0], frame_values=[2.0])
        t3 = MetricTrace([0], frame_values=[0.0])
        result = ArithmeticOperator([t1, t2, t3], 'arithmetic').run(op='divide', num_inputs=3)
        assert result.frame_values == [None]


class TestArithmeticAbsResult:
    """Test abs_result parameter."""

    def test_abs_result_subtract(self):
        t1 = MetricTrace([0, 100], frame_values=[3.0, 10.0])
        t2 = MetricTrace([0, 100], frame_values=[5.0, 4.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='subtract', abs_result=True)
        assert result.frame_values == [2.0, 6.0]

    def test_abs_result_add_negative(self):
        t1 = MetricTrace([0, 100], frame_values=[-5.0, -3.0])
        t2 = MetricTrace([0, 100], frame_values=[-2.0, -1.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='add', abs_result=True)
        assert result.frame_values == [7.0, 4.0]

    def test_abs_result_false_preserves_sign(self):
        t1 = MetricTrace([0], frame_values=[3.0])
        t2 = MetricTrace([0], frame_values=[5.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='subtract', abs_result=False)
        assert result.frame_values == [-2.0]

    def test_abs_result_with_none_preserved(self):
        t1 = MetricTrace([0, 100], frame_values=[None, -5.0])
        t2 = MetricTrace([0, 100], frame_values=[3.0, 2.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='subtract', abs_result=True)
        assert result.frame_values == [None, 7.0]

    def test_abs_result_divide_by_zero_still_none(self):
        t1 = MetricTrace([0], frame_values=[10.0])
        t2 = MetricTrace([0], frame_values=[0.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='divide', abs_result=True)
        assert result.frame_values == [None]


class TestArithmeticNonePropagation:
    """Test None propagation behavior."""

    def test_none_in_first_input(self):
        t1 = MetricTrace([0, 100, 200], frame_values=[None, 2.0, 3.0])
        t2 = MetricTrace([0, 100, 200], frame_values=[4.0, 5.0, 6.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='add')
        assert result.frame_values == [None, 7.0, 9.0]

    def test_none_in_second_input(self):
        t1 = MetricTrace([0, 100], frame_values=[1.0, 2.0])
        t2 = MetricTrace([0, 100], frame_values=[3.0, None])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='multiply')
        assert result.frame_values == [3.0, None]

    def test_none_in_all_inputs(self):
        t1 = MetricTrace([0], frame_values=[None])
        t2 = MetricTrace([0], frame_values=[None])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='add')
        assert result.frame_values == [None]


class TestArithmeticEmptyTraces:
    """Test with empty traces."""

    def test_empty_frame_values(self):
        t1 = MetricTrace([], frame_values=[])
        t2 = MetricTrace([], frame_values=[])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='add')
        assert result.frame_values == []


class TestArithmeticInvalidOp:
    """Test invalid operation raises error."""

    def test_unknown_op(self):
        t1 = MetricTrace([0], frame_values=[1.0])
        t2 = MetricTrace([0], frame_values=[2.0])
        with pytest.raises(ValueError, match="Unknown arithmetic op"):
            ArithmeticOperator([t1, t2], 'arithmetic').run(op='invalid')

    def test_modulo_rejected(self):
        t1 = MetricTrace([0], frame_values=[1.0])
        t2 = MetricTrace([0], frame_values=[2.0])
        with pytest.raises(ValueError, match="Unknown arithmetic op"):
            ArithmeticOperator([t1, t2], 'arithmetic').run(op='modulo')


class TestArithmeticNumInputs:
    """Test num_inputs validation."""

    def test_default_num_inputs_matches_two(self):
        t1 = MetricTrace([0, 100], frame_values=[1.0, 2.0])
        t2 = MetricTrace([0, 100], frame_values=[3.0, 4.0])
        result = ArithmeticOperator([t1, t2], 'arithmetic').run(op='add')
        assert result.frame_values == [4.0, 6.0]

    def test_num_inputs_mismatch_too_few(self):
        t1 = MetricTrace([0], frame_values=[1.0])
        t2 = MetricTrace([0], frame_values=[2.0])
        with pytest.raises(ValueError, match="Expected 3 input traces, got 2"):
            ArithmeticOperator([t1, t2], 'arithmetic').run(op='add', num_inputs=3)

    def test_num_inputs_mismatch_too_many(self):
        t1 = MetricTrace([0], frame_values=[1.0])
        t2 = MetricTrace([0], frame_values=[2.0])
        t3 = MetricTrace([0], frame_values=[3.0])
        with pytest.raises(ValueError, match="Expected 2 input traces, got 3"):
            ArithmeticOperator([t1, t2, t3], 'arithmetic').run(op='add', num_inputs=2)


class TestArithmeticWrapperFunction:
    """Test the arithmetic() wrapper function."""

    def test_wrapper_add(self):
        t1 = MetricTrace([0, 100], frame_values=[1.0, 2.0])
        t2 = MetricTrace([0, 100], frame_values=[3.0, 4.0])
        result = arithmetic([t1, t2], op='add')
        assert result.frame_values == [4.0, 6.0]

    def test_wrapper_subtract(self):
        t1 = MetricTrace([0, 100], frame_values=[10.0, 20.0])
        t2 = MetricTrace([0, 100], frame_values=[3.0, 5.0])
        result = arithmetic([t1, t2], op='subtract')
        assert result.frame_values == [7.0, 15.0]

    def test_wrapper_abs_result(self):
        t1 = MetricTrace([0], frame_values=[3.0])
        t2 = MetricTrace([0], frame_values=[5.0])
        result = arithmetic([t1, t2], op='subtract', abs_result=True)
        assert result.frame_values == [2.0]

    def test_wrapper_num_inputs(self):
        t1 = MetricTrace([0], frame_values=[2.0])
        t2 = MetricTrace([0], frame_values=[3.0])
        t3 = MetricTrace([0], frame_values=[4.0])
        result = arithmetic([t1, t2, t3], op='multiply', num_inputs=3)
        assert result.frame_values == [24.0]


class TestArithmeticRegistration:
    """Test operator registration and discovery."""

    def test_in_operator_mapping(self):
        assert "arithmetic" in OPERATOR_MAPPING
        assert OPERATOR_MAPPING["arithmetic"] is ArithmeticOperator

    def test_import_from_init(self):
        assert ArithmeticOperatorFromInit is ArithmeticOperator

    def test_discovery_api(self):
        api = OperatorDiscoveryAPI()
        info = api.get_operator_info("arithmetic")
        assert info["name"] == "arithmetic"
        assert info["class_name"] == "ArithmeticOperator"

    def test_discovery_api_enums(self):
        enums = OperatorDiscoveryAPI.KNOWN_ENUMS
        assert "arithmetic" in enums
        assert enums["arithmetic"]["op"] == ["add", "subtract", "multiply", "divide"]
        assert "abs_result" not in enums["arithmetic"]
