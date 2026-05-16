"""DAG Evaluator - Evaluates metric DAGs over scenario data.

This module provides the DAGEvaluator class which evaluates a MetricDAG
over scenario data by:
1. Fetching monitor results using MonitorEvaluator
2. Following the DAG structure to execute operators
3. Combining leaf node results with AND logic to produce a final boolean
"""

import json
import time
import networkx as nx
from typing import Dict, List, Optional, Union, Any, Type
from humex.metrics.metric_trace import MetricTrace
from humex.metrics.monitors.monitor_evaluator import MonitorEvaluator
from humex.metrics.operators import (
    CompareOperator,
    ReduceOperator,
    AggregateOperator,
    TransformOperator,
    MaskOperator,
    ObserveOperator,
    DurationOperator,
    WithinOperator,
    LogicOperator,
    ArithmeticOperator,
    ScenarioWindowOperator,
    ChainResultOperator,
)

try:
    from humex.proto import metric_result_pb2
except ImportError:
    metric_result_pb2 = None

# Mapping of operator names to their corresponding classes
# This allows dynamic instantiation of operators based on DAG node configuration
OPERATOR_MAPPING: Dict[str, Type] = {
    "compare": CompareOperator,
    "reduce": ReduceOperator,
    "aggregate": AggregateOperator,
    "transform": TransformOperator,
    "mask": MaskOperator,
    "observe": ObserveOperator,
    "duration": DurationOperator,
    "within": WithinOperator,
    "logic": LogicOperator,
    "arithmetic": ArithmeticOperator,
    "scenario_window": ScenarioWindowOperator,
    "chain_result": ChainResultOperator,
}


class DAGEvaluator:
    """Evaluates a MetricDAG over scenario data to produce final pass/fail result.

    The evaluator:
    1. Fetches monitor results from the scenario
    2. Traverses the DAG in topological order
    3. Executes operators at each node using parent node results
    4. Combines leaf node boolean results with AND logic
    5. Returns detailed evaluation results

    Attributes:
        scenario: Loaded scenario with all frames, map, signal data
        dag: MetricDAG instance with node definitions
        node_results: Dict mapping node_id to result (MetricTrace or bool)
        evaluation_complete: Flag indicating if evaluation has run
    """

    def __init__(self, scenario, metric_dag, logs=None):
        """Initialize DAGEvaluator with scenario and DAG.

        Args:
            scenario: Scenario object with loaded frames and metadata
            metric_dag: MetricDAG instance with node definitions
            logs: Optional list to append log messages to (for API responses)

        Example:
            >>> from humex.metrics.dag.dag_evaluator import DAGEvaluator
            >>> evaluator = DAGEvaluator(scenario, dag)
            >>> results = evaluator.evaluate()
        """
        self.scenario = scenario
        self.dag = metric_dag
        self.node_results = {}  # {node_id: MetricTrace or bool}
        self.evaluation_complete = False
        self.evaluation_time = 0.0
        self.logs = logs if logs is not None else []

    def _log(self, msg):
        print(msg)
        self.logs.append(msg)

    def evaluate(self) -> Dict[str, Any]:
        """Evaluate the DAG over the scenario data.

        Returns a dictionary with final result and detailed intermediate results.

        Returns:
            dict: Evaluation results containing:
                - final_result: Boolean result (True/False/None)
                - node_results: Dict of all node evaluation results
                - leaf_nodes: List of leaf node results
                - metadata: Evaluation metadata

        Raises:
            ValueError: If DAG structure is invalid or evaluation fails
        """
        start_time = time.time()

        try:
            # Step 1: Get all monitor results
            self._get_monitor_results()

            # Step 2: Traverse DAG and evaluate each node
            self._evaluate_dag_nodes()

            # Step 3: Combine leaf node results
            final_result = self._combine_leaf_results()

            # Step 4: Prepare detailed results
            results = self._prepare_results(final_result)

            self.evaluation_complete = True
            self.evaluation_time = time.time() - start_time

            self._log(f"DAG evaluation result: {final_result} ({len(self.node_results)} nodes evaluated in {self.evaluation_time:.3f}s)")

            return results

        except Exception as e:
            self.evaluation_complete = False
            raise ValueError(f"DAG evaluation failed: {str(e)}") from e

    def _get_monitor_results(self) -> None:
        """Fetch monitor results from MonitorEvaluator.

        Identifies all monitor nodes in the DAG. For mock_monitor nodes, builds
        MetricTrace directly from node params. For real monitors, uses
        MonitorEvaluator with scenario data.

        Raises:
            ValueError: If monitor evaluation fails
        """
        # Separate mock_monitor nodes from real monitor nodes
        mock_nodes = {}  # node_id -> node
        real_monitor_info = {}  # name -> params

        for node_id, node in self.dag.nodes.items():
            if node.type != "monitor":
                continue
            monitor_name = getattr(node, "name", None)
            if monitor_name == "mock_monitor":
                mock_nodes[node_id] = node
            elif monitor_name:
                real_monitor_info[monitor_name] = getattr(node, "params", {}) or {}

        # Handle mock_monitor nodes: build traces from params
        for node_id, node in mock_nodes.items():
            params = getattr(node, "params", {}) or {}
            trace = self._build_mock_trace(params, node_id)
            self.node_results[node_id] = trace

        # Handle real monitors (only if there are any)
        if real_monitor_info:
            self.monitor_evaluator = MonitorEvaluator(self.scenario, logs=self.logs)

            for monitor_name, params in real_monitor_info.items():
                try:
                    self.monitor_evaluator.add(monitor_name, params=params)
                except ValueError as e:
                    raise ValueError(f"Monitor '{monitor_name}' not found: {str(e)}")

            monitor_results = self.monitor_evaluator.run()

            for node_id, node in self.dag.nodes.items():
                if node.type == "monitor":
                    monitor_name = getattr(node, "name", None)
                    if monitor_name in monitor_results:
                        trace = monitor_results[monitor_name]
                        trace.source_monitors = [node_id]
                        self.node_results[node_id] = trace

    @staticmethod
    def _build_mock_trace(params: Dict[str, Any], node_id: int) -> MetricTrace:
        """Build a MetricTrace from mock_monitor params.

        Args:
            params: Dict with frame_values (JSON string), frame_duration, output_type
            node_id: Node ID to set as source_monitors

        Returns:
            MetricTrace with populated timestamps, frame_values, segments, and source_monitors
        """
        # Parse frame_values from JSON string or use directly if already a list
        raw_values = params.get("frame_values", "[]")
        if isinstance(raw_values, str):
            frame_values = json.loads(raw_values)
        else:
            frame_values = list(raw_values)

        frame_duration = float(params.get("frame_duration", 0.1))
        output_type = params.get("output_type", "float")

        # Cast values to the specified type
        type_casters = {
            "float": float,
            "bool": lambda v: bool(v) if not isinstance(v, bool) else v,
            "int": int,
            "string": str,
        }
        caster = type_casters.get(output_type, lambda v: v)
        frame_values = [None if v is None else caster(v) for v in frame_values]

        # Generate timestamps as int64 nanoseconds
        duration_ns = int(frame_duration * 1_000_000_000)
        timestamps = [i * duration_ns for i in range(len(frame_values))]

        # Default segment: full range
        if timestamps:
            segments = [(timestamps[0], timestamps[-1])]
        else:
            segments = []

        trace = MetricTrace(
            timestamps=timestamps,
            frame_values=frame_values,
            segments=segments,
        )
        trace.source_monitors = [node_id]
        return trace

    def _evaluate_dag_nodes(self) -> None:
        """Evaluate all nodes in the DAG following topological order.

        Traverses the DAG in topological order and evaluates each node:
        - Monitors: results already in node_results
        - Operators: instantiate and execute with input from parent nodes

        Raises:
            ValueError: If operator execution fails
        """
        # Topological sort ensures parents are evaluated before children
        for node_id in nx.topological_sort(self.dag.graph):
            node = self.dag.nodes[node_id]

            # Monitors already evaluated
            if node.type == "monitor":
                continue

            # Operators need to be executed
            if node.type == "operator":
                self._log(f"Evaluating operator node {node.id}: {getattr(node, 'name', 'unknown')} (inputs: {node.inputs})")
                self._execute_operator_node(node)

    def _execute_operator_node(self, node) -> None:
        """Execute a single operator node.

        Retrieves input from parent nodes, instantiates the operator,
        executes it with node parameters, and stores the result.

        Args:
            node: Node object representing the operator

        Raises:
            ValueError: If operator instantiation or execution fails
        """
        # Collect inputs from parent nodes
        inputs = self._collect_node_inputs(node)

        # Instantiate and execute operator
        operator_result = self._execute_operator(node, inputs)

        # Store result
        self.node_results[node.id] = operator_result

    def _collect_node_inputs(self, node) -> Dict[int, Union[MetricTrace, Any]]:
        """Collect input MetricTraces from parent nodes.

        Args:
            node: Node whose inputs to collect

        Returns:
            dict: Mapping of input node_id to their results
        """
        inputs = {}
        for input_id in node.inputs:
            if input_id in self.node_results:
                inputs[input_id] = self.node_results[input_id]
            else:
                raise ValueError(f"Input node {input_id} not found in results")
        return inputs

    def _execute_operator(self, node, inputs: Dict) -> Union[MetricTrace, bool]:
        """Execute a single operator with given inputs.

        Dynamically instantiates the operator class from OPERATOR_MAPPING based on
        the operator name stored in node.name, then executes it with the provided
        input MetricTrace and node parameters.

        Args:
            node: Operator node with type='operator', name (operator type), and params
            inputs: Dict of input node results (node_id -> result)

        Returns:
            MetricTrace or bool: Result of operator execution

        Raises:
            ValueError: If operator type is unknown, has no inputs, or execution fails
        """
        operator_name = getattr(node, "name", "unknown")

        # Get ordered list of input traces based on node.inputs order
        ordered_inputs = [inputs[input_id] for input_id in node.inputs if input_id in inputs]

        if not ordered_inputs:
            raise ValueError(f"Operator {operator_name} has no inputs")

        # Operators that require multiple inputs
        multi_input_operators = {"mask", "logic", "arithmetic"}

        if operator_name in multi_input_operators and len(ordered_inputs) > 1:
            # Pass list of traces for multi-input operators
            input_data = ordered_inputs
            # Validate all inputs are MetricTrace
            for i, trace in enumerate(input_data):
                if not isinstance(trace, MetricTrace):
                    raise ValueError(
                        f"Operator {operator_name} expects MetricTrace inputs, "
                        f"got {type(trace)} at position {i}"
                    )
        else:
            # Single input mode
            input_data = ordered_inputs[0]
            if not isinstance(input_data, MetricTrace):
                raise ValueError(
                    f"Operator {operator_name} expects MetricTrace input, got {type(input_data)}"
                )

        # Look up operator class from mapping
        if operator_name not in OPERATOR_MAPPING:
            raise ValueError(
                f"Unknown operator: {operator_name}. "
                f"Supported operators: {list(OPERATOR_MAPPING.keys())}"
            )

        try:
            # Instantiate operator class dynamically
            operator_class = OPERATOR_MAPPING[operator_name]
            operator_instance = operator_class(input_data, operator_name)

            # Execute operator with parameters from DAG node
            # The **node.params allows all parameters to flow directly from the DAG
            return operator_instance.run(**(node.params or {}))

        except Exception as e:
            raise ValueError(
                f"Error executing operator '{operator_name}': {str(e)}"
            ) from e

    def _combine_leaf_results(self) -> Optional[bool]:
        """Combine leaf node results using AND logic.

        Finds all leaf nodes (nodes with no outgoing edges) and combines
        their boolean results using AND logic.

        Returns:
            bool or None: Final combined result (True/False/None)
        """
        # Find leaf nodes (no outgoing edges)
        leaf_nodes = [
            node_id
            for node_id in self.dag.graph.nodes()
            if self.dag.graph.out_degree(node_id) == 0
        ]

        if not leaf_nodes:
            return None

        # Extract boolean values from leaf nodes
        leaf_values = []
        for node_id in leaf_nodes:
            node = self.dag.nodes[node_id]
            if getattr(node, "name", "") == "observe":
                continue

            result = self.node_results.get(node_id)

            # Extract boolean from result
            bool_value = self._extract_boolean(result)
            if bool_value is not None:
                leaf_values.append(bool_value)

        # Apply AND logic
        if not leaf_values:
            return None

        return all(leaf_values)

    def _extract_boolean(self, result: Any) -> Optional[bool]:
        """Extract a boolean value from evaluation result.

        Handles MetricTrace and direct boolean values. Uses the same logic
        as protobuf conversion to ensure final_result and per-leaf
        reduced_result are always consistent.

        Args:
            result: Result from operator (MetricTrace or bool)

        Returns:
            bool or None: Extracted boolean value
        """
        if result is None:
            return None

        # If already boolean
        if isinstance(result, bool):
            return result

        # If MetricTrace, extract boolean result
        if isinstance(result, MetricTrace):
            # Prefer reduced_result (set by compare operator)
            if result.reduced_result is not None:
                return bool(result.reduced_result)
            # Fall back to AND of frame_results (set by compare operator)
            if result.frame_results:
                bool_frames = [bool(f) for f in result.frame_results if f is not None]
                return all(bool_frames) if bool_frames else None
            # No compare operator applied — no boolean result available
            return None

        return None

    def _prepare_results(self, final_result: Optional[bool]) -> Dict[str, Any]:
        """Prepare final results dictionary.

        Args:
            final_result: Final boolean result

        Returns:
            dict: Complete evaluation results
        """
        # Collect leaf node details
        leaf_nodes = [
            node_id
            for node_id in self.dag.graph.nodes()
            if self.dag.graph.out_degree(node_id) == 0
        ]

        chain_names = self._derive_chain_names(leaf_nodes)

        leaf_node_details = []
        for node_id in leaf_nodes:
            node = self.dag.nodes[node_id]
            result = self.node_results.get(node_id)

            if getattr(node, "name", "") == "observe":
                bool_value = None
            else:
                bool_value = self._extract_boolean(result)

            leaf_node_details.append(
                {
                    "id": node_id,
                    "name": chain_names.get(node_id, getattr(node, "name", f"node_{node_id}")),
                    "type": node.type,
                    "result": bool_value,
                }
            )

        return {
            "final_result": final_result,
            "node_results": self.node_results,
            "leaf_nodes": leaf_node_details,
            "metadata": {
                "dag_description": self.dag.metadata.get("description", ""),
                "evaluation_time_seconds": self.evaluation_time,
                "nodes_evaluated": len(self.node_results),
                "total_nodes": len(self.dag.nodes),
            },
        }

    def _derive_chain_names(self, leaf_node_ids: List[int]) -> Dict[int, str]:
        """Derive metric chain names from upstream monitors for each leaf node.

        Each chain is named after its root monitor(s). Uses the monitor's
        node_name (display name) if set, otherwise the monitor type name.
        If multiple chains share the same monitor name, appends _1, _2, etc.

        Args:
            leaf_node_ids: List of leaf node IDs

        Returns:
            Dict mapping leaf node ID to its chain name
        """
        # For each leaf, find all ancestor monitor nodes
        leaf_monitors: Dict[int, List[str]] = {}
        for leaf_id in leaf_node_ids:
            monitors = []
            for ancestor_id in nx.ancestors(self.dag.graph, leaf_id):
                ancestor = self.dag.nodes.get(ancestor_id)
                if ancestor and ancestor.type == "monitor":
                    name = getattr(ancestor, "node_name", None) or getattr(ancestor, "name", f"monitor_{ancestor_id}")
                    monitors.append(name)
            # Also check the leaf itself (in case it's a monitor with no operators)
            leaf_node = self.dag.nodes.get(leaf_id)
            if leaf_node and leaf_node.type == "monitor":
                name = getattr(leaf_node, "node_name", None) or getattr(leaf_node, "name", f"monitor_{leaf_id}")
                monitors.append(name)
            leaf_monitors[leaf_id] = sorted(set(monitors))

        # Build raw chain names (join monitor names if multiple)
        raw_names: Dict[int, str] = {}
        for leaf_id, monitors in leaf_monitors.items():
            if monitors:
                raw_names[leaf_id] = "+".join(monitors)
            else:
                raw_names[leaf_id] = ""

        # Deduplicate: if multiple leaves have the same raw name, add _1, _2 suffixes
        name_counts: Dict[str, List[int]] = {}
        for leaf_id, name in raw_names.items():
            if not name:
                continue
            name_counts.setdefault(name, []).append(leaf_id)

        result: Dict[int, str] = {}
        for name, ids in name_counts.items():
            if len(ids) == 1:
                result[ids[0]] = name
            else:
                # Sort by node ID for stable ordering
                for idx, leaf_id in enumerate(sorted(ids), 1):
                    result[leaf_id] = f"{name}_{idx}"

        return result

    def save_to_proto(self, results: Dict[str, Any]) -> 'metric_result_pb2.MetricResult':
        """Convert evaluation results to MetricResult protobuf message.

        Creates a pure data structure with leaf node evaluation results.
        No business logic or interpretation - just raw DAG evaluation data.

        Args:
            results: Evaluation results dictionary from evaluate()

        Returns:
            MetricResult protobuf message ready for serialization

        Raises:
            ImportError: If humex.proto module is not available
        """
        if metric_result_pb2 is None:
            raise ImportError("humex.proto module not available for protobuf serialization")

        # Identify all leaf nodes (nodes with no outgoing edges)
        leaf_nodes = [
            node_id
            for node_id in self.dag.graph.nodes()
            if self.dag.graph.out_degree(node_id) == 0
        ]

        # Derive chain names from upstream monitors for each leaf node.
        # Each chain is named after its root monitor(s). If multiple chains
        # share the same monitor name, add _1, _2 suffixes.
        leaf_chain_names = self._derive_chain_names(leaf_nodes)

        # Create leaf node results for each leaf
        leaf_node_results = []
        for node_id in leaf_nodes:
            node = self.dag.nodes[node_id]
            result_trace = self.node_results.get(node_id)

            if isinstance(result_trace, MetricTrace):
                # Use derived chain name, fall back to analyzer_names > node_name > node.name
                node_name = leaf_chain_names.get(node_id, "")
                if not node_name:
                    analyzer_names = getattr(node, "analyzer_names", [])
                    if analyzer_names and len(analyzer_names) > 0:
                        node_name = analyzer_names[0]
                    elif getattr(node, "node_name", None):
                        node_name = node.node_name
                    else:
                        node_name = getattr(node, "name", "")

                # Create frame-level results
                frame_results = []
                has_frame_results = result_trace.frame_results and len(result_trace.frame_results) > 0
                has_frame_values = result_trace.frame_values and len(result_trace.frame_values) > 0
                if has_frame_results or has_frame_values:
                    for i, ts in enumerate(result_trace.timestamps):
                        if has_frame_results and i >= len(result_trace.frame_results):
                            break
                        if has_frame_values and i >= len(result_trace.frame_values):
                            break

                        frame_result = metric_result_pb2.MetricLeafFrameResult()
                        frame_result.timestamp = ts

                        # Set frame value (try different types)
                        frame_val = result_trace.frame_values[i] if i < len(result_trace.frame_values) else None
                        if isinstance(frame_val, bool):
                            frame_result.boolean_value = frame_val
                        elif isinstance(frame_val, (int, float)):
                            frame_result.numeric_value = float(frame_val)
                        elif frame_val is not None:
                            frame_result.string_value = str(frame_val)

                        # Set frame result (boolean evaluation result) if available
                        if has_frame_results:
                            frame_result.frame_result = bool(result_trace.frame_results[i])

                        frame_results.append(frame_result)

                # Create leaf node result
                leaf_node_result = metric_result_pb2.MetricLeafNodeResult()
                leaf_node_result.node_id = node_id
                leaf_node_result.name = node_name
                leaf_node_result.frame_results.extend(frame_results)
                leaf_node_result.source_monitor_ids.extend(result_trace.source_monitors)

                # Set reduced value (aggregated result)
                if result_trace.reduced_value is not None:
                    if isinstance(result_trace.reduced_value, bool):
                        leaf_node_result.boolean_reduced = result_trace.reduced_value
                    elif isinstance(result_trace.reduced_value, (int, float)):
                        leaf_node_result.numeric_reduced = float(result_trace.reduced_value)
                    else:
                        leaf_node_result.string_reduced = str(result_trace.reduced_value)

                # Set reduced result (scenario-level boolean result)
                if result_trace.reduced_result is not None:
                    leaf_node_result.reduced_result = bool(result_trace.reduced_result)
                elif result_trace.frame_results:
                    # No reduce operator or reduce didn't set result — derive from frame results
                    bool_frames = [bool(f) for f in result_trace.frame_results if f is not None]
                    if bool_frames:
                        leaf_node_result.reduced_result = all(bool_frames)

                leaf_node_results.append(leaf_node_result)

        # Create overall MetricResult (pure data, no business logic)
        dag_result = metric_result_pb2.MetricResult()
        dag_result.dag_description = self.dag.metadata.get("description", "")
        dag_result.leaf_node_results.extend(leaf_node_results)
        dag_result.final_result = bool(results.get("final_result", False))
        dag_result.evaluation_time_seconds = results["metadata"]["evaluation_time_seconds"]
        dag_result.nodes_evaluated = results["metadata"]["nodes_evaluated"]
        dag_result.total_nodes = results["metadata"]["total_nodes"]

        # Set evaluation timestamp in nanoseconds
        import time as time_module
        dag_result.evaluation_timestamp = int(time_module.time() * 1e9)

        # Add all node results (monitors + operators) for detailed inspection
        for node_id in self.dag.nodes.keys():
            node = self.dag.nodes[node_id]
            result_trace = self.node_results.get(node_id)

            if isinstance(result_trace, MetricTrace):
                all_node_result = metric_result_pb2.MetricAllNodeResult()
                all_node_result.node_id = node_id
                all_node_result.node_type = node.type  # "monitor" or "operator"
                all_node_result.name = getattr(node, "node_name", "") or getattr(node, "name", "")

                # Add input IDs for operators
                if hasattr(node, "inputs") and node.inputs:
                    all_node_result.input_ids.extend(node.inputs)

                # Add params for operators
                if hasattr(node, "params") and node.params:
                    for key, value in node.params.items():
                        all_node_result.params[key] = str(value)

                # Add frame-level results
                for i, ts in enumerate(result_trace.timestamps):
                    frame_result = metric_result_pb2.MetricLeafFrameResult()
                    frame_result.timestamp = ts

                    # Set frame value
                    if i < len(result_trace.frame_values):
                        frame_val = result_trace.frame_values[i]
                        if isinstance(frame_val, bool):
                            frame_result.boolean_value = frame_val
                        elif isinstance(frame_val, (int, float)):
                            frame_result.numeric_value = float(frame_val)
                        elif frame_val is not None:
                            frame_result.string_value = str(frame_val)

                    # Set frame result if available
                    if result_trace.frame_results and i < len(result_trace.frame_results):
                        frame_result.frame_result = bool(result_trace.frame_results[i])

                    all_node_result.frame_results.append(frame_result)

                dag_result.all_node_results.append(all_node_result)

        return dag_result
