"""Tests for TestDagMetricsAPI - mock monitor evaluation."""

import pytest
import tempfile
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from humex.api.metrics_api.test_dag_metrics_api import TestDagMetricsAPI


def _write_dag_yaml(content: str) -> str:
    """Write DAG YAML content to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


# Simple DAG: ego_collision -> reduce(any) -> compare(== False)
SIMPLE_COLLISION_DAG = """\
description: "Simple collision check"
nodes:
  1:
    type: monitor
    name: ego_collision
  2:
    type: operator
    name: reduce
    inputs: [1]
    params:
      op: any
  3:
    type: operator
    name: compare
    inputs: [2]
    params:
      op_symbol: "=="
      threshold: false
"""

# DAG with two monitors: ego_collision and ego_speed
TWO_MONITOR_DAG = """\
description: "Collision and speed check"
nodes:
  1:
    type: monitor
    name: ego_collision
  2:
    type: operator
    name: reduce
    inputs: [1]
    params:
      op: any
  3:
    type: operator
    name: compare
    inputs: [2]
    params:
      op_symbol: "=="
      threshold: false
  4:
    type: monitor
    name: ego_speed
  5:
    type: operator
    name: reduce
    inputs: [4]
    params:
      op: max
  6:
    type: operator
    name: compare
    inputs: [5]
    params:
      op_symbol: "<="
      threshold: 30.0
"""

# --- mock_monitor DAGs (params-based, no separate mock_monitors dict) ---

MOCK_MONITOR_BOOL_DAG = """\
description: "Mock monitor bool test"
nodes:
  1:
    type: monitor
    name: mock_monitor
    params:
      frame_values: "[false, false, true, true, true]"
      frame_duration: 0.1
      output_type: "bool"
  2:
    type: operator
    name: reduce
    inputs: [1]
    params:
      op: any
  3:
    type: operator
    name: compare
    inputs: [2]
    params:
      op_symbol: "=="
      threshold: false
"""

MOCK_MONITOR_FLOAT_DAG = """\
description: "Mock monitor float test"
nodes:
  1:
    type: monitor
    name: mock_monitor
    params:
      frame_values: "[10.0, 20.0, 25.0]"
      frame_duration: 0.1
      output_type: "float"
  2:
    type: operator
    name: reduce
    inputs: [1]
    params:
      op: max
  3:
    type: operator
    name: compare
    inputs: [2]
    params:
      op_symbol: "<="
      threshold: 30.0
"""

MOCK_MONITOR_TWO_DAG = """\
description: "Two mock monitors"
nodes:
  1:
    type: monitor
    name: mock_monitor
    params:
      frame_values: "[false, false, false]"
      frame_duration: 0.1
      output_type: "bool"
  2:
    type: operator
    name: reduce
    inputs: [1]
    params:
      op: any
  3:
    type: operator
    name: compare
    inputs: [2]
    params:
      op_symbol: "=="
      threshold: false
  4:
    type: monitor
    name: mock_monitor
    params:
      frame_values: "[10.0, 20.0, 25.0]"
      frame_duration: 0.1
      output_type: "float"
  5:
    type: operator
    name: reduce
    inputs: [4]
    params:
      op: max
  6:
    type: operator
    name: compare
    inputs: [5]
    params:
      op_symbol: "<="
      threshold: 30.0
"""


class TestTestDagMetricsAPI:
    """Test suite for TestDagMetricsAPI."""

    def test_basic_passing_case(self):
        """All-False collision values -> reduce(any)=False -> compare(==False)=True."""
        dag_path = _write_dag_yaml(SIMPLE_COLLISION_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(
                dag_yaml_path=dag_path,
                mock_monitors={
                    "ego_collision": {
                        "frame_values": [False, False, False, False, False],
                        "frame_duration": 0.1,
                    },
                },
            )
            assert result["final_result"] is True
        finally:
            os.unlink(dag_path)

    def test_basic_failing_case(self):
        """Last frame True collision -> compare(==False) last frame = False -> fail."""
        dag_path = _write_dag_yaml(SIMPLE_COLLISION_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(
                dag_yaml_path=dag_path,
                mock_monitors={
                    "ego_collision": {
                        "frame_values": [False, False, True, True, True],
                        "frame_duration": 0.1,
                    },
                },
            )
            # Last frame: True == False -> False, so final_result is False
            assert result["final_result"] is False
        finally:
            os.unlink(dag_path)

    def test_missing_mock_data_raises(self):
        """Missing mock data for a monitor node raises ValueError."""
        dag_path = _write_dag_yaml(SIMPLE_COLLISION_DAG)
        try:
            api = TestDagMetricsAPI()
            with pytest.raises(ValueError, match="no mock data"):
                api.compute(
                    dag_yaml_path=dag_path,
                    mock_monitors={},  # No mock data
                )
        finally:
            os.unlink(dag_path)

    def test_multiple_mock_monitors(self):
        """DAG with two monitors: both passing."""
        dag_path = _write_dag_yaml(TWO_MONITOR_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(
                dag_yaml_path=dag_path,
                mock_monitors={
                    "ego_collision": {
                        "frame_values": [False, False, False],
                        "frame_duration": 0.1,
                    },
                    "ego_speed": {
                        "frame_values": [10.0, 20.0, 25.0],
                        "frame_duration": 0.1,
                    },
                },
            )
            # No collision (pass) AND max speed 25 <= 30 (pass) -> True
            assert result["final_result"] is True
        finally:
            os.unlink(dag_path)

    def test_multiple_monitors_one_failing(self):
        """DAG with two monitors: speed exceeds limit."""
        dag_path = _write_dag_yaml(TWO_MONITOR_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(
                dag_yaml_path=dag_path,
                mock_monitors={
                    "ego_collision": {
                        "frame_values": [False, False, False],
                        "frame_duration": 0.1,
                    },
                    "ego_speed": {
                        "frame_values": [10.0, 20.0, 35.0],
                        "frame_duration": 0.1,
                    },
                },
            )
            # No collision (pass) AND max speed 35 > 30 (fail) -> False
            assert result["final_result"] is False
        finally:
            os.unlink(dag_path)

    def test_custom_frame_duration(self):
        """Custom frame_duration generates correct timestamps."""
        dag_path = _write_dag_yaml(SIMPLE_COLLISION_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(
                dag_yaml_path=dag_path,
                mock_monitors={
                    "ego_collision": {
                        "frame_values": [False, False],
                        "frame_duration": 0.05,  # 20Hz
                    },
                },
            )
            # Check timestamps in monitor node result
            monitor_trace = result["node_results"][1]
            assert monitor_trace.timestamps == [0, 50_000_000]
            assert result["final_result"] is True
        finally:
            os.unlink(dag_path)

    def test_custom_segments(self):
        """Custom segments are passed through to MetricTrace."""
        dag_path = _write_dag_yaml(SIMPLE_COLLISION_DAG)
        try:
            api = TestDagMetricsAPI()
            custom_segments = [(0, 200_000_000)]
            result = api.compute(
                dag_yaml_path=dag_path,
                mock_monitors={
                    "ego_collision": {
                        "frame_values": [False, False, False],
                        "frame_duration": 0.1,
                        "segments": custom_segments,
                    },
                },
            )
            monitor_trace = result["node_results"][1]
            assert monitor_trace.segments == custom_segments
        finally:
            os.unlink(dag_path)

    def test_empty_frame_values(self):
        """Empty frame_values produces empty MetricTrace."""
        dag_path = _write_dag_yaml(SIMPLE_COLLISION_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(
                dag_yaml_path=dag_path,
                mock_monitors={
                    "ego_collision": {
                        "frame_values": [],
                        "frame_duration": 0.1,
                    },
                },
            )
            monitor_trace = result["node_results"][1]
            assert len(monitor_trace.timestamps) == 0
            assert len(monitor_trace.frame_values) == 0
            assert monitor_trace.segments == []
        finally:
            os.unlink(dag_path)

    def test_dag_file_not_found(self):
        """Non-existent DAG YAML raises FileNotFoundError."""
        api = TestDagMetricsAPI()
        with pytest.raises(FileNotFoundError):
            api.compute(
                dag_yaml_path="/nonexistent/path.yaml",
                mock_monitors={"ego_collision": {"frame_values": [False]}},
            )

    def test_result_structure(self):
        """Verify result dict has expected keys."""
        dag_path = _write_dag_yaml(SIMPLE_COLLISION_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(
                dag_yaml_path=dag_path,
                mock_monitors={
                    "ego_collision": {
                        "frame_values": [False, False],
                        "frame_duration": 0.1,
                    },
                },
            )
            assert "final_result" in result
            assert "node_results" in result
            assert "leaf_nodes" in result
            assert "metadata" in result
            assert "logs" in result
        finally:
            os.unlink(dag_path)

    def test_default_segment_full_range(self):
        """Default segment spans first to last timestamp."""
        dag_path = _write_dag_yaml(SIMPLE_COLLISION_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(
                dag_yaml_path=dag_path,
                mock_monitors={
                    "ego_collision": {
                        "frame_values": [False, False, False, False],
                        "frame_duration": 0.1,
                    },
                },
            )
            monitor_trace = result["node_results"][1]
            assert monitor_trace.segments == [(0, 300_000_000)]
        finally:
            os.unlink(dag_path)


class TestMockMonitorCatalog:
    """Tests for mock_monitor as a catalog monitor (params-based, no mock_monitors dict)."""

    def test_mock_monitor_bool_passing(self):
        """mock_monitor with all-false bool values -> reduce(any)=False -> pass."""
        dag_yaml = """\
description: "Mock bool passing"
nodes:
  1:
    type: monitor
    name: mock_monitor
    params:
      frame_values: "[false, false, false]"
      frame_duration: 0.1
      output_type: "bool"
  2:
    type: operator
    name: reduce
    inputs: [1]
    params:
      op: any
  3:
    type: operator
    name: compare
    inputs: [2]
    params:
      op_symbol: "=="
      threshold: false
"""
        dag_path = _write_dag_yaml(dag_yaml)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(dag_yaml_path=dag_path)
            assert result["final_result"] is True
        finally:
            os.unlink(dag_path)

    def test_mock_monitor_bool_failing(self):
        """mock_monitor with some true bool values -> reduce(any)=True -> fail."""
        dag_path = _write_dag_yaml(MOCK_MONITOR_BOOL_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(dag_yaml_path=dag_path)
            assert result["final_result"] is False
        finally:
            os.unlink(dag_path)

    def test_mock_monitor_float_passing(self):
        """mock_monitor with float values, max <= threshold -> pass."""
        dag_path = _write_dag_yaml(MOCK_MONITOR_FLOAT_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(dag_yaml_path=dag_path)
            assert result["final_result"] is True
        finally:
            os.unlink(dag_path)

    def test_mock_monitor_float_failing(self):
        """mock_monitor with float values, max > threshold -> fail."""
        dag_yaml = """\
description: "Mock float failing"
nodes:
  1:
    type: monitor
    name: mock_monitor
    params:
      frame_values: "[10.0, 20.0, 35.0]"
      frame_duration: 0.1
      output_type: "float"
  2:
    type: operator
    name: reduce
    inputs: [1]
    params:
      op: max
  3:
    type: operator
    name: compare
    inputs: [2]
    params:
      op_symbol: "<="
      threshold: 30.0
"""
        dag_path = _write_dag_yaml(dag_yaml)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(dag_yaml_path=dag_path)
            assert result["final_result"] is False
        finally:
            os.unlink(dag_path)

    def test_mock_monitor_two_monitors(self):
        """Two mock_monitor nodes in one DAG, both passing."""
        dag_path = _write_dag_yaml(MOCK_MONITOR_TWO_DAG)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(dag_yaml_path=dag_path)
            assert result["final_result"] is True
        finally:
            os.unlink(dag_path)

    def test_mock_monitor_timestamps(self):
        """mock_monitor generates correct timestamps from frame_duration."""
        dag_yaml = """\
description: "Timestamp check"
nodes:
  1:
    type: monitor
    name: mock_monitor
    params:
      frame_values: "[1.0, 2.0, 3.0]"
      frame_duration: 0.05
      output_type: "float"
  2:
    type: operator
    name: reduce
    inputs: [1]
    params:
      op: max
"""
        dag_path = _write_dag_yaml(dag_yaml)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(dag_yaml_path=dag_path)
            monitor_trace = result["node_results"][1]
            assert monitor_trace.timestamps == [0, 50_000_000, 100_000_000]
        finally:
            os.unlink(dag_path)

    def test_mock_monitor_default_segments(self):
        """mock_monitor generates default segment spanning full range."""
        dag_yaml = """\
description: "Segment check"
nodes:
  1:
    type: monitor
    name: mock_monitor
    params:
      frame_values: "[1.0, 2.0, 3.0, 4.0]"
      frame_duration: 0.1
      output_type: "float"
  2:
    type: operator
    name: reduce
    inputs: [1]
    params:
      op: max
"""
        dag_path = _write_dag_yaml(dag_yaml)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(dag_yaml_path=dag_path)
            monitor_trace = result["node_results"][1]
            assert monitor_trace.segments == [(0, 300_000_000)]
        finally:
            os.unlink(dag_path)

    def test_mock_monitor_non_mock_without_dict_raises(self):
        """Non-mock_monitor node without mock_monitors dict raises ValueError."""
        dag_path = _write_dag_yaml(SIMPLE_COLLISION_DAG)
        try:
            api = TestDagMetricsAPI()
            with pytest.raises(ValueError, match="not a mock_monitor"):
                api.compute(dag_yaml_path=dag_path)
        finally:
            os.unlink(dag_path)

    def test_mock_monitor_discovery(self):
        """mock_monitor is discoverable via monitor_mapping."""
        from humex.metrics.monitors import monitor_mapping
        assert "mock_monitor" in monitor_mapping

    def test_mock_monitor_discovery_api(self):
        """mock_monitor params are visible via MonitorDiscoveryAPI."""
        from humex.api.metrics_api import MonitorDiscoveryAPI
        api = MonitorDiscoveryAPI()
        info = api.get_monitor_info("mock_monitor")
        assert info["name"] == "mock_monitor"
        param_names = [p["name"] for p in info["parameters"]]
        assert "frame_values" in param_names
        assert "frame_duration" in param_names
        assert "output_type" in param_names
