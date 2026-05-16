"""Mock DAG Evaluator - Evaluates metric DAGs with mock monitor data.

Subclasses DAGEvaluator to inject predefined MetricTrace objects instead of
reading from real scenarios. All operator evaluation logic is inherited unchanged.
"""

from typing import Dict, List, Any, Optional
from humex.metrics.metric_trace import MetricTrace
from humex.metrics.dag.dag_evaluator import DAGEvaluator


class MockDAGEvaluator(DAGEvaluator):
    """Evaluates a MetricDAG using mock monitor data instead of real scenarios.

    Overrides only _get_monitor_results() to build MetricTrace objects from
    user-provided frame values and durations. All operator evaluation logic
    (topological traversal, operator execution, leaf combination) is inherited.

    Args:
        metric_dag: MetricDAG instance with node definitions
        mock_monitors: Dict mapping monitor names to mock data dicts with keys:
            - frame_values: List of values for each frame
            - frame_duration: Seconds between frames (e.g., 0.1 for 10Hz)
            - segments: Optional list of (start_ts, end_ts) tuples
        logs: Optional list to append log messages to
    """

    def __init__(self, metric_dag, mock_monitors: Dict[str, Dict[str, Any]], logs=None):
        super().__init__(scenario=None, metric_dag=metric_dag, logs=logs)
        self.mock_monitors = mock_monitors

    def _get_monitor_results(self) -> None:
        """Build MetricTrace objects from mock monitor data.

        For each monitor node in the DAG, looks up mock data by node name,
        builds a MetricTrace with auto-generated timestamps, and stores it
        in self.node_results.

        Raises:
            ValueError: If a monitor node has no corresponding mock data
        """
        for node_id, node in self.dag.nodes.items():
            if node.type != "monitor":
                continue

            # Look up by node_name first (user display name), then fall back to name (type)
            monitor_name = getattr(node, "node_name", None) or getattr(node, "name", None)
            if monitor_name not in self.mock_monitors:
                # Try the other name as fallback
                fallback = getattr(node, "name", None)
                if fallback and fallback in self.mock_monitors:
                    monitor_name = fallback
                else:
                    raise ValueError(
                        f"Monitor node '{monitor_name}' (id={node_id}) has no mock data. "
                        f"Available mock monitors: {list(self.mock_monitors.keys())}"
                    )

            mock_data = self.mock_monitors[monitor_name]
            trace = self._build_mock_trace(mock_data, node_id)
            self.node_results[node_id] = trace

    @staticmethod
    def _build_mock_trace(mock_data: Dict[str, Any], node_id: int) -> MetricTrace:
        """Build a MetricTrace from mock monitor data.

        Generates int64 nanosecond timestamps from frame_duration, creates a
        default segment spanning the full time range if none provided.

        Args:
            mock_data: Dict with frame_values, frame_duration, and optional segments
            node_id: Node ID to set as source_monitors

        Returns:
            MetricTrace with populated timestamps, frame_values, segments, and source_monitors
        """
        frame_values = mock_data["frame_values"]
        frame_duration = mock_data.get("frame_duration", 0.1)

        # Generate timestamps as int64 nanoseconds
        duration_ns = int(frame_duration * 1_000_000_000)
        timestamps = [i * duration_ns for i in range(len(frame_values))]

        # Default segment: full range
        if "segments" in mock_data:
            segments = [tuple(s) for s in mock_data["segments"]]
        elif timestamps:
            segments = [(timestamps[0], timestamps[-1])]
        else:
            segments = []

        trace = MetricTrace(
            timestamps=timestamps,
            frame_values=list(frame_values),
            segments=segments,
        )
        trace.source_monitors = [node_id]
        return trace
