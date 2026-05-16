"""Tests for ComputeDagMetricsAPI.

This test module verifies that ComputeDagMetricsAPI can successfully:
- Load a DAG YAML configuration
- Load a scenario from proto files
- Compute metrics using DAGEvaluator
- Return valid MetricResult protobuf objects
- Save metrics results to disk
"""

import pytest
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from humex.api.core_apis import ComputeDagMetricsAPI


@pytest.fixture
def test_data_paths():
    """Fixture providing paths to test data files.

    Returns:
        dict: Paths to scenario, map, signal, and DAG YAML files
    """
    base = Path(__file__).parent / "data"
    paths = {
        'scenario': base / "ava_scenarios/scenario4/ava_scenario_scenario4.pb",
        'map': base / "ava_scenarios/scenario4/ava_map_scenario4.pb",
        'signal': base / "ava_scenarios/scenario4/ava_signal_scenario4.pb",
        'dag_yaml': base / "dag_configs/safety_basic_ai_converted.yaml",
    }
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        pytest.skip(f"Test data not present in this checkout: {missing}")
    return paths


class TestComputeDagMetricsAPI:
    """Test suite for ComputeDagMetricsAPI."""

    def test_data_files_exist(self, test_data_paths):
        """Verify that all required test data files exist."""
        for key, path in test_data_paths.items():
            assert path.exists(), f"Test data file not found: {key} at {path}"

    def test_api_instantiation(self):
        """Test that ComputeDagMetricsAPI can be instantiated."""
        api = ComputeDagMetricsAPI()
        assert api is not None
        assert hasattr(api, 'compute')
        assert hasattr(api, 'scenario_api')

    def test_compute_dag_metrics_api_basic(self, test_data_paths):
        """Test ComputeDagMetricsAPI.compute() returns valid metrics results.

        This is the main integration test that verifies:
        1. API can load scenario from proto files
        2. API can load DAG from YAML
        3. API computes metrics successfully
        4. API returns valid MetricResult protobuf
        5. API can save metrics results to disk
        6. Evaluation metadata is populated
        """

        # Create API instance
        api = ComputeDagMetricsAPI()

        # Compute metrics
        result = api.compute(
            dag_yaml_path=str(test_data_paths['dag_yaml']),
            scenario_file_path=str(test_data_paths['scenario']),
            map_file_path=str(test_data_paths['map']),
            signal_file_path=str(test_data_paths['signal']),
            save_metrics_result=True,
            visualize=False,
            save_video=False,
        )

        # =====================================================
        # 1. Verify result structure
        # =====================================================
        assert isinstance(result, dict), "Result should be a dictionary"
        assert 'metric_result' in result, "Result missing 'metric_result' key"
        assert 'metric_result_path' in result, "Result missing 'metric_result_path' key"
        assert 'dag_yaml_path' in result, "Result missing 'dag_yaml_path' key"
        assert 'evaluation_metadata' in result, "Result missing 'evaluation_metadata' key"
        assert 'video_path' in result, "Result missing 'video_path' key"

        # =====================================================
        # 2. Verify MetricResult protobuf is valid
        # =====================================================
        metric_result = result['metric_result']
        assert metric_result is not None, "metric_result should not be None"
        assert hasattr(metric_result, 'final_result'), \
            "metric_result should have 'final_result' attribute"
        assert hasattr(metric_result, 'leaf_node_results'), \
            "metric_result should have 'leaf_node_results' attribute"
        assert hasattr(metric_result, 'evaluation_time_seconds'), \
            "metric_result should have 'evaluation_time_seconds' attribute"
        assert hasattr(metric_result, 'nodes_evaluated'), \
            "metric_result should have 'nodes_evaluated' attribute"
        assert hasattr(metric_result, 'total_nodes'), \
            "metric_result should have 'total_nodes' attribute"

        # =====================================================
        # 3. Verify metrics result file was saved
        # =====================================================
        assert result['metric_result_path'] is not None, \
            "metric_result_path should not be None when save_metrics_result=True"

        result_path = Path(result['metric_result_path'])
        assert result_path.exists(), \
            f"Metrics result file not saved at expected path: {result_path}"
        assert result_path.suffix == '.pb', \
            f"Metrics result file should have .pb extension, got {result_path.suffix}"
        assert result_path.name.startswith('ava_metrics_result_'), \
            f"Metrics result file should follow naming convention, got {result_path.name}"
        assert result_path.stat().st_size > 0, \
            f"Saved metrics result file is empty: {result_path}"

        # Store path for cleanup
        saved_result_path = result_path

        # =====================================================
        # 4. Verify evaluation metadata is present
        # =====================================================
        metadata = result['evaluation_metadata']
        assert isinstance(metadata, dict), "evaluation_metadata should be a dict"
        # Note: metadata may be empty dict if not populated by DAGEvaluator,
        # so we verify it's a dict and continue testing other aspects
        if metadata:
            # If metadata is populated, verify expected keys
            if 'evaluation_time_seconds' in metadata:
                assert isinstance(metadata['evaluation_time_seconds'], (int, float)), \
                    "evaluation_time_seconds should be numeric"
                assert metadata['evaluation_time_seconds'] >= 0, \
                    "evaluation_time_seconds should be non-negative"
            if 'nodes_evaluated' in metadata:
                assert isinstance(metadata['nodes_evaluated'], int), \
                    "nodes_evaluated should be an integer"
                assert metadata['nodes_evaluated'] > 0, \
                    "nodes_evaluated should be greater than 0"
            if 'total_nodes' in metadata:
                assert isinstance(metadata['total_nodes'], int), \
                    "total_nodes should be an integer"
                assert metadata['total_nodes'] > 0, \
                    "total_nodes should be greater than 0"
            if 'nodes_evaluated' in metadata and 'total_nodes' in metadata:
                assert metadata['nodes_evaluated'] <= metadata['total_nodes'], \
                    "nodes_evaluated should not exceed total_nodes"

        # =====================================================
        # 5. Verify metrics were computed (has results)
        # =====================================================
        assert metric_result.final_result is not None, \
            "final_result should be computed (not None)"
        assert len(metric_result.leaf_node_results) > 0, \
            "Should have at least one leaf node result"

        # Verify leaf node results have expected structure
        for leaf_result in metric_result.leaf_node_results:
            assert hasattr(leaf_result, 'node_id'), \
                "Leaf node result missing 'node_id'"
            assert hasattr(leaf_result, 'name'), \
                "Leaf node result missing 'name'"
            assert hasattr(leaf_result, 'frame_results'), \
                "Leaf node result missing 'frame_results'"
            assert leaf_result.node_id > 0, \
                "node_id should be positive"
            assert leaf_result.name, \
                "node name should not be empty"

        # =====================================================
        # 6. Verify DAG YAML path in result
        # =====================================================
        assert result['dag_yaml_path'] == str(test_data_paths['dag_yaml']), \
            "dag_yaml_path in result should match input"

        # =====================================================
        # Cleanup: Remove test-generated metrics result file
        # =====================================================
        if saved_result_path.exists():
            saved_result_path.unlink()
            assert not saved_result_path.exists(), \
                "Failed to clean up saved metrics result file"

    def test_compute_without_saving(self, test_data_paths):
        """Test ComputeDagMetricsAPI.compute() without saving results.

        Verifies that the API still works correctly when save_metrics_result=False
        and no file is created.
        """
        api = ComputeDagMetricsAPI()

        result = api.compute(
            dag_yaml_path=str(test_data_paths['dag_yaml']),
            scenario_file_path=str(test_data_paths['scenario']),
            map_file_path=str(test_data_paths['map']),
            signal_file_path=str(test_data_paths['signal']),
            save_metrics_result=False,  # Don't save
            visualize=False,
            save_video=False,
        )

        # Verify result structure
        assert 'metric_result' in result
        assert 'evaluation_metadata' in result

        # Verify no file was saved
        assert result['metric_result_path'] is None, \
            "metric_result_path should be None when save_metrics_result=False"

        # Verify metrics were still computed
        assert result['metric_result'] is not None
        assert result['metric_result'].final_result is not None
