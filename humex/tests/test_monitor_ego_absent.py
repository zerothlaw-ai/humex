"""Tests that monitors return None when the ego vehicle is absent from the frame."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from humex.components.frame import Frame

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scenario(ego_id=0):
    """Create a minimal mock scenario with no map (sufficient for ego-absent tests)."""
    scenario = MagicMock()
    scenario.ego_id = ego_id
    scenario.map = None
    return scenario


def _make_empty_frame(timestamp=0):
    """Create a frame with no objects so get_ego() returns None."""
    return Frame(timestamp=timestamp)


# ---------------------------------------------------------------------------
# Phase 1: Simple monitors — ego absent → None
# ---------------------------------------------------------------------------

class TestSimpleMonitorsEgoAbsent:
    """Each simple monitor must return None when ego is not in the frame."""

    def _run_monitor(self, monitor_cls, scenario=None, params=None):
        scenario = scenario or _make_scenario()
        if params is not None:
            monitor = monitor_cls(scenario, params=params)
        else:
            monitor = monitor_cls(scenario)
        frame = _make_empty_frame()
        monitor.curr_frame = frame
        return monitor.calculate()

    def test_ego_speed(self):
        from humex.metrics.monitors.catalog.ego_speed import EgoSpeed
        assert self._run_monitor(EgoSpeed) is None

    def test_ego_acceleration(self):
        from humex.metrics.monitors.catalog.ego_acceleration import EgoAcceleration
        assert self._run_monitor(EgoAcceleration) is None

    def test_ego_lane_speed_limit(self):
        from humex.metrics.monitors.catalog.ego_lane_speed_limit import EgoLaneSpeedLimit
        assert self._run_monitor(EgoLaneSpeedLimit) is None

    def test_ego_speed_excess(self):
        from humex.metrics.monitors.catalog.ego_speed_excess import EgoSpeedExcess
        assert self._run_monitor(EgoSpeedExcess) is None

    def test_ego_collision(self):
        from humex.metrics.monitors.catalog.ego_collision import EgoCollision
        assert self._run_monitor(EgoCollision) is None

    def test_ego_out_of_map(self):
        from humex.metrics.monitors.catalog.ego_out_of_map import EgoOutOfMap
        scenario = _make_scenario()
        scenario.map = MagicMock()
        scenario.map.map_data.lanes = {}
        assert self._run_monitor(EgoOutOfMap, scenario=scenario) is None

    def test_ego_center_offset(self):
        from humex.metrics.monitors.catalog.ego_center_offset import EgoCenterOffset
        assert self._run_monitor(EgoCenterOffset) is None

    def test_ego_yaw_rate(self):
        from humex.metrics.monitors.catalog.ego_yaw_rate import EgoYawRate
        assert self._run_monitor(EgoYawRate) is None

    def test_ego_lat_accel(self):
        from humex.metrics.monitors.catalog.ego_lat_accel import EgoLatAccel
        assert self._run_monitor(EgoLatAccel) is None

    def test_ego_lon_accel(self):
        from humex.metrics.monitors.catalog.ego_lon_accel import EgoLonAccel
        assert self._run_monitor(EgoLonAccel) is None

    def test_ego_lon_jerk(self):
        from humex.metrics.monitors.catalog.ego_lon_jerk import EgoLonJerk
        assert self._run_monitor(EgoLonJerk) is None

    def test_stop_line_crossed(self):
        from humex.metrics.monitors.catalog.stop_line_crossed import StopLineCrossed
        scenario = _make_scenario()
        scenario.map = MagicMock()
        scenario.map.map_data.lanes = {}
        assert self._run_monitor(StopLineCrossed, scenario=scenario) is None

    def test_object_within_ego_buffer(self):
        from humex.metrics.monitors.catalog.object_within_ego_buffer import ObjectWithinEgoBuffer
        assert self._run_monitor(ObjectWithinEgoBuffer, params={}) is None

    def test_lateral_distance(self):
        from humex.metrics.monitors.catalog.lateral_distance import LateralDistance
        assert self._run_monitor(LateralDistance) is None

    def test_front_vehicle_distance(self):
        from humex.metrics.monitors.catalog.front_vehicle_distance import FrontVehicleDistance
        assert self._run_monitor(FrontVehicleDistance) is None

    def test_front_vehicle_id(self):
        from humex.metrics.monitors.catalog.front_vehicle_id import FrontVehicleId
        assert self._run_monitor(FrontVehicleId) is None


# ---------------------------------------------------------------------------
# Phase 2: Compound monitors — None propagation from sub-monitors
# ---------------------------------------------------------------------------

class TestCompoundMonitorsEgoAbsent:
    """Compound monitors must return None when their sub-monitors return None (ego absent)."""

    def test_ttc_front_vehicle(self):
        from humex.metrics.monitors.catalog.ttc_front_vehicle import TtcFrontVehicle
        scenario = _make_scenario()
        monitor = TtcFrontVehicle(scenario, params={})
        frame = _make_empty_frame()
        monitor.curr_frame = frame
        result = monitor.calculate()
        assert result is None

    def test_time_headway(self):
        from humex.metrics.monitors.catalog.time_headway import TimeHeadway
        scenario = _make_scenario()
        monitor = TimeHeadway(scenario)
        frame = _make_empty_frame()
        monitor.curr_frame = frame
        result = monitor.calculate()
        assert result is None


# ---------------------------------------------------------------------------
# Phase 3: Pipeline integration — None frames excluded by operators
# ---------------------------------------------------------------------------

def _write_dag_yaml(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


class TestPipelineNonePropagation:
    """Verify that None values from monitors flow correctly through compare → reduce."""

    def test_mixed_none_and_real_values_compare_reduce(self):
        """None frames should be excluded by reduce; real values processed normally."""
        from humex.api.metrics_api.test_dag_metrics_api import TestDagMetricsAPI

        # DAG: mock_monitor → compare("> 5") → reduce(any)
        # Values: [None, 10.0, None, 3.0, None]
        # After compare: [None, True, None, False, None]
        # reduce(any) filters None → any([True, False]) = True
        dag_yaml = """\
description: "None propagation test"
nodes:
  1:
    type: monitor
    name: mock_monitor
    params:
      frame_values: "[null, 10.0, null, 3.0, null]"
      frame_duration: 0.1
      output_type: "float"
  2:
    type: operator
    name: compare
    inputs: [1]
    params:
      op_symbol: ">"
      threshold: 5.0
  3:
    type: operator
    name: reduce
    inputs: [2]
    params:
      op: any
"""
        dag_path = _write_dag_yaml(dag_yaml)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(dag_yaml_path=dag_path)
            # Node 3 is the reduce node — check the MetricTrace directly
            reduce_trace = result["node_results"][3]
            assert reduce_trace.reduced_value is True
        finally:
            os.unlink(dag_path)

    def test_all_none_values_reduce_all(self):
        """When all values are None, reduce(all) should default to True (empty-case)."""
        from humex.api.metrics_api.test_dag_metrics_api import TestDagMetricsAPI

        dag_yaml = """\
description: "All None reduce test"
nodes:
  1:
    type: monitor
    name: mock_monitor
    params:
      frame_values: "[null, null, null]"
      frame_duration: 0.1
      output_type: "float"
  2:
    type: operator
    name: compare
    inputs: [1]
    params:
      op_symbol: "<="
      threshold: 10.0
  3:
    type: operator
    name: reduce
    inputs: [2]
    params:
      op: all
"""
        dag_path = _write_dag_yaml(dag_yaml)
        try:
            api = TestDagMetricsAPI()
            result = api.compute(dag_yaml_path=dag_path)
            # reduce(all) with all None → empty → defaults to True
            reduce_trace = result["node_results"][3]
            assert reduce_trace.reduced_value is True
        finally:
            os.unlink(dag_path)
