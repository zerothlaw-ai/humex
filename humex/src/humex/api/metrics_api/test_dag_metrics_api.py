"""API for testing metric DAGs with mock monitor data.

Allows users to define mock monitors with predefined frame values/durations,
wire them into a DAG with operators, and evaluate — getting identical results
to real scenario evaluation without needing maps, agents, or simulation data.

Returns the same MetricResult protobuf as compute-dag, so Zeno can display
test results identically to real evaluation results.

Supports two modes:
1. mock_monitor nodes in the DAG YAML (preferred) — no separate mock_monitors dict needed
2. Explicit mock_monitors dict (backward compatible) — for non-catalog mock data

Usage (mock_monitor nodes):
    >>> from humex.api import TestDagMetricsAPI
    >>> api = TestDagMetricsAPI()
    >>> result = api.compute(dag_yaml_path="data/dag_cfg/my_dag.yaml")
    >>> print(result['metric_result_path'])

Usage (explicit mock_monitors):
    >>> result = api.compute(
    ...     dag_yaml_path="data/dag_cfg/my_dag.yaml",
    ...     mock_monitors={
    ...         "ego_speed": {
    ...             "frame_values": [10.0, 15.0, 20.0, 25.0, 30.0],
    ...             "frame_duration": 0.1,
    ...         },
    ...     },
    ... )
"""

import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from humex.metrics.dag.dag import MetricDAG
from humex.metrics.dag.dag_evaluator import DAGEvaluator
from humex.metrics.dag.mock_dag_evaluator import MockDAGEvaluator


class TestDagMetricsAPI:
    """API for testing metric DAGs with mock monitor data.

    Enables rapid iteration on metric definitions by evaluating DAG operator
    chains with predefined monitor values, without requiring real scenario data.
    Produces the same MetricResult protobuf as compute-dag.
    """

    def compute(
        self,
        dag_yaml_path: str,
        mock_monitors: Optional[Dict[str, Dict[str, Any]]] = None,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate a DAG YAML with mock monitor data.

        If mock_monitors is not provided, all monitor nodes must be mock_monitor
        nodes with frame_values/frame_duration/output_type in their params.

        Args:
            dag_yaml_path: Path to DAG YAML configuration file
            mock_monitors: Optional dict mapping monitor names to mock data:
                - frame_values: List of values for each frame
                - frame_duration: Seconds between frames (default 0.1)
                - segments: Optional list of (start_ts, end_ts) tuples
            output_dir: Directory to write the result protobuf. When provided,
                the .pb file is written here instead of the system temp
                directory, which is important for cross-container access.

        Returns:
            Dictionary with keys:
            - 'final_result': bool or None - AND of all leaf node results
            - 'metric_result_path': str - Path to saved MetricResult protobuf
            - 'leaf_nodes': list - Leaf node detail dicts
            - 'metadata': dict - Evaluation metadata
            - 'logs': list - Log messages from evaluation

        Raises:
            FileNotFoundError: If DAG YAML path doesn't exist
            ValueError: If DAG is invalid or mock data is missing for a monitor
        """
        # 1. Validate DAG YAML path
        dag_path = Path(dag_yaml_path)
        if not dag_path.exists():
            raise FileNotFoundError(f"DAG YAML file not found: {dag_yaml_path}")

        # 2. Load DAG from YAML
        dag = MetricDAG()
        dag.load_from_yaml(str(dag_path))

        logs = []

        if mock_monitors is not None:
            # Legacy path: explicit mock_monitors dict
            # Validate that all monitor nodes have corresponding mock data
            # Look up by node_name first (user display name), then fall back to name (type)
            for node_id, node in dag.nodes.items():
                if node.type == "monitor":
                    monitor_name = getattr(node, "node_name", None) or getattr(node, "name", None)
                    if monitor_name not in mock_monitors:
                        fallback = getattr(node, "name", None)
                        if not (fallback and fallback in mock_monitors):
                            display_names = [
                                getattr(n, "node_name", None) or n.name
                                for n in dag.nodes.values() if n.type == 'monitor'
                            ]
                            raise ValueError(
                                f"Monitor node '{monitor_name}' (id={node_id}) has no mock data. "
                                f"Provide mock data for all monitor nodes: {display_names}"
                            )
            evaluator = MockDAGEvaluator(dag, mock_monitors, logs=logs)
        else:
            # New path: all monitors must be mock_monitor nodes (handled by DAGEvaluator)
            for node_id, node in dag.nodes.items():
                if node.type == "monitor":
                    monitor_name = getattr(node, "name", None)
                    if monitor_name != "mock_monitor":
                        raise ValueError(
                            f"Monitor node '{monitor_name}' (id={node_id}) is not a mock_monitor. "
                            f"When mock_monitors dict is not provided, all monitor nodes must "
                            f"be mock_monitor with frame_values in params."
                        )
            evaluator = DAGEvaluator(scenario=None, metric_dag=dag, logs=logs)

        results = evaluator.evaluate()

        # 3. Convert to protobuf and save (same as compute-dag)
        metric_result_proto = evaluator.save_to_proto(results)

        dag_name = dag_path.stem
        metric_result_path = None
        try:
            if output_dir:
                # Write to caller-specified directory (e.g. shared workspace volume)
                out = Path(output_dir)
                out.mkdir(parents=True, exist_ok=True)
                result_file = out / f"test_dag_{dag_name}_{uuid.uuid4().hex[:12]}.pb"
                result_file.write_bytes(metric_result_proto.SerializeToString())
                metric_result_path = str(result_file)
            else:
                # Fallback to system temp (fine for single-process / local dev)
                fd, tmp_path = tempfile.mkstemp(suffix='.pb', prefix=f'test_dag_{dag_name}_')
                with open(fd, 'wb') as f:
                    f.write(metric_result_proto.SerializeToString())
                metric_result_path = tmp_path
            logs.append(f"Metrics result saved to {metric_result_path}")
        except Exception as e:
            logs.append(f"Warning: Failed to save metrics result: {str(e)}")

        results["metric_result_path"] = metric_result_path
        results["logs"] = logs
        return results
