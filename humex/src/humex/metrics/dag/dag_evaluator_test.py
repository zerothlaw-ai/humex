"""Test DAGEvaluator functionality.

This module tests the DAGEvaluator class to verify:
1. Monitor result fetching from MonitorEvaluator
2. Operator instantiation and execution
3. Topological DAG traversal
4. Leaf node combination with AND logic
5. Final result computation

Note: Full integration tests require scenario data files that may not be available.
This test file includes unit tests that can run without external scenario files.
"""

from pathlib import Path
from humex.metrics.dag.dag import MetricDAG
from humex.metrics.dag.dag_node import DagNode
from humex.metrics.dag.dag_evaluator import DAGEvaluator
from humex.metrics.metric_trace import MetricTrace


def test_dag_structure_and_initialization():
    """Test DAG structure and DAGEvaluator initialization."""
    print("Test 1: DAG Structure and Initialization")
    print("=" * 60)

    # Create a simple DAG manually
    dag = MetricDAG()
    dag.metadata["description"] = "Test DAG"

    # Add nodes
    monitor_node = DagNode(
        id=1,
        type="monitor",
        instance=None,
        inputs=[],
        params={},
        description="Monitor node",
        tags=[],
        analyzer_names=[],
        name="test_monitor"
    )
    dag.add_node(monitor_node)

    operator_node = DagNode(
        id=2,
        type="operator",
        instance=None,
        inputs=[1],
        params={"op": "all"},
        description="Reduce operator",
        tags=[],
        analyzer_names=[],
        name="reduce"
    )
    dag.add_node(operator_node)

    print(f"✓ Created test DAG with {len(dag.nodes)} nodes")

    # Create evaluator (without scenario - for structure testing)
    # We'll pass None as scenario since we're just testing initialization
    try:
        evaluator = DAGEvaluator(None, dag)
        print(f"✓ DAGEvaluator initialized successfully")
        print(f"  DAG nodes: {len(evaluator.dag.nodes)}")
        print(f"  DAG description: {evaluator.dag.metadata['description']}")
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")

    print()


def test_extract_boolean_from_metric_trace():
    """Test boolean extraction from MetricTrace values."""
    print("Test 2: Boolean Extraction from MetricTrace")
    print("=" * 60)

    dag = MetricDAG()
    evaluator = DAGEvaluator(None, dag)

    # Test cases for _extract_boolean
    test_cases = [
        (None, None, "None input"),
        (True, True, "Direct boolean True"),
        (False, False, "Direct boolean False"),
        (MetricTrace(timestamps=[0], frame_values=[True]), True, "MetricTrace with True"),
        (MetricTrace(timestamps=[0], frame_values=[False]), False, "MetricTrace with False"),
        (MetricTrace(timestamps=[0, 100], frame_values=[True, False]), False, "MetricTrace last value False"),
        (MetricTrace(timestamps=[0, 100], frame_values=[False, True]), True, "MetricTrace last value True"),
        (MetricTrace(timestamps=[], frame_values=[]), None, "Empty MetricTrace"),
    ]

    print(f"✓ Testing boolean extraction:")
    for input_val, expected, description in test_cases:
        result = evaluator._extract_boolean(input_val)
        status = "✓" if result == expected else "✗"
        print(
            f"  {status} {description:40} → {result} (expected {expected})"
        )
        assert result == expected, f"Failed for {description}"

    print()


def test_leaf_node_combination():
    """Test leaf node AND logic combination."""
    print("Test 3: Leaf Node AND Logic Combination")
    print("=" * 60)

    dag = MetricDAG()
    evaluator = DAGEvaluator(None, dag)

    # Test case 1: Simple linear DAG with leaf node
    print("✓ Test case 1: Single leaf node")
    dag1 = MetricDAG()

    leaf_node = DagNode(
        id=1,
        type="operator",
        instance=None,
        inputs=[],
        params={},
        description="Leaf node",
        tags=[],
        analyzer_names=[],
        name="reduce"
    )
    dag1.add_node(leaf_node)

    evaluator1 = DAGEvaluator(None, dag1)
    evaluator1.node_results[1] = MetricTrace(timestamps=[0], frame_values=[True])

    result = evaluator1._combine_leaf_results()
    print(f"  Single leaf (True): {result} (expected True)")
    assert result == True

    # Test case 2: Multiple leaf nodes - AND logic
    print("✓ Test case 2: Multiple leaf nodes with AND logic")
    dag2 = MetricDAG()

    leaf_node1 = DagNode(id=1, type="operator", instance=None, inputs=[], params={}, description="", tags=[], analyzer_names=[], name="reduce")
    leaf_node2 = DagNode(id=2, type="operator", instance=None, inputs=[], params={}, description="", tags=[], analyzer_names=[], name="reduce")

    dag2.add_node(leaf_node1)
    dag2.add_node(leaf_node2)

    evaluator2 = DAGEvaluator(None, dag2)
    evaluator2.node_results[1] = MetricTrace(timestamps=[0], frame_values=[True])
    evaluator2.node_results[2] = MetricTrace(timestamps=[0], frame_values=[True])

    result = evaluator2._combine_leaf_results()
    print(f"  Two leaves (True, True): {result} (expected True)")
    assert result == True

    # Test case 3: Multiple leaves with one False
    evaluator2.node_results[2] = MetricTrace(timestamps=[0], frame_values=[False])
    result = evaluator2._combine_leaf_results()
    print(f"  Two leaves (True, False): {result} (expected False)")
    assert result == False

    print()


def test_prepare_results_format():
    """Test that evaluator returns results in expected format."""
    print("Test 4: Result Format Verification")
    print("=" * 60)

    dag = MetricDAG()
    dag.metadata["description"] = "Test DAG"

    # Add two nodes: one monitor (root), one operator (leaf)
    monitor_node = DagNode(id=1, type="monitor", instance=None, inputs=[], params={}, description="", tags=[], analyzer_names=[], name="test_monitor")
    dag.add_node(monitor_node)

    operator_node = DagNode(id=2, type="operator", instance=None, inputs=[1], params={}, description="", tags=[], analyzer_names=[], name="reduce")
    dag.add_node(operator_node)

    evaluator = DAGEvaluator(None, dag)
    # Populate node results
    evaluator.node_results[1] = MetricTrace(timestamps=[0], frame_values=[1.0])
    evaluator.node_results[2] = MetricTrace(timestamps=[0], frame_values=[True])

    # Prepare results (without full evaluation)
    results = evaluator._prepare_results(True)

    print("✓ Verifying result structure:")

    # Check top-level keys
    required_keys = ["final_result", "node_results", "leaf_nodes", "metadata"]
    for key in required_keys:
        assert key in results, f"Missing key: {key}"
        print(f"  ✓ {key}: present")

    # Check final_result type
    assert isinstance(results["final_result"], (bool, type(None)))
    print(f"  ✓ final_result type: {type(results['final_result']).__name__}")

    # Check node_results
    assert isinstance(results["node_results"], dict)
    print(f"  ✓ node_results: {len(results['node_results'])} entries")

    # Check leaf_nodes
    assert isinstance(results["leaf_nodes"], list)
    print(f"  ✓ leaf_nodes: {len(results['leaf_nodes'])} leaves")

    # Verify leaf node structure
    for leaf in results["leaf_nodes"]:
        assert "id" in leaf
        assert "name" in leaf
        assert "type" in leaf
        assert "result" in leaf
        print(f"  ✓ Leaf node {leaf['id']}: {leaf['name']} = {leaf['result']}")

    # Check metadata
    metadata = results["metadata"]
    assert "dag_description" in metadata
    assert "evaluation_time_seconds" in metadata
    assert "nodes_evaluated" in metadata
    assert "total_nodes" in metadata
    print(f"  ✓ metadata: valid")

    print()


def test_collect_node_inputs():
    """Test collecting inputs from parent nodes."""
    print("Test 5: Collect Node Inputs")
    print("=" * 60)

    dag = MetricDAG()

    # Create parent and child nodes
    parent_node = DagNode(id=1, type="operator", instance=None, inputs=[], params={}, description="", tags=[], analyzer_names=[], name="reduce")

    child_node = DagNode(id=2, type="operator", instance=None, inputs=[1], params={}, description="", tags=[], analyzer_names=[], name="compare")

    dag.add_node(parent_node)
    dag.add_node(child_node)

    evaluator = DAGEvaluator(None, dag)

    # Test 1: Collect inputs for child node
    parent_result = MetricTrace(timestamps=[0, 100], frame_values=[1.0, 2.0])
    evaluator.node_results[1] = parent_result

    inputs = evaluator._collect_node_inputs(child_node)
    print(f"✓ Collected inputs for node {child_node.id}:")
    print(f"  Input nodes: {list(inputs.keys())}")
    assert 1 in inputs, "Should have input from node 1"
    assert inputs[1] == parent_result
    print(f"  ✓ Input from node 1: MetricTrace with {len(parent_result.frame_values)} values")

    # Test 2: Missing input should raise error
    print(f"✓ Test missing input handling:")
    node_with_missing_input = DagNode(id=3, type="operator", instance=None, inputs=[999], params={}, description="", tags=[], analyzer_names=[])
    try:
        evaluator._collect_node_inputs(node_with_missing_input)
        print(f"  ✗ Should have raised ValueError")
    except ValueError as e:
        print(f"  ✓ Correctly raised ValueError: {e}")

    print()


def test_unknown_operator_error():
    """Test error handling for unknown operator types."""
    print("Test 6: Unknown Operator Error Handling")
    print("=" * 60)

    dag = MetricDAG()

    # Create node with unknown operator name
    unknown_op_node = DagNode(
        id=1,
        type="operator",
        instance=None,
        inputs=[],
        params={},
        description="Unknown operator",
        tags=[],
        analyzer_names=[],
        name="nonexistent_operator"
    )

    evaluator = DAGEvaluator(None, dag)
    input_trace = MetricTrace(timestamps=[0], frame_values=[1.0])
    inputs = {0: input_trace}

    print("✓ Testing unknown operator error handling:")
    try:
        evaluator._execute_operator(unknown_op_node, inputs)
        print(f"  ✗ Should have raised ValueError for unknown operator")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        error_msg = str(e)
        print(f"  ✓ Correctly raised ValueError:")
        print(f"    {error_msg}")
        assert "Unknown operator" in error_msg
        assert "nonexistent_operator" in error_msg
        assert "Supported operators" in error_msg
        print(f"  ✓ Error message includes supported operators list")

    print()


if __name__ == "__main__":
    print("\n")
    print("=" * 60)
    print("DAGEvaluator Unit Tests")
    print("=" * 60)
    print()

    try:
        test_dag_structure_and_initialization()
        test_extract_boolean_from_metric_trace()
        test_leaf_node_combination()
        test_prepare_results_format()
        test_collect_node_inputs()
        test_unknown_operator_error()

        print("=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ Test failed with error:")
        print(f"  {type(e).__name__}: {str(e)}")
        import traceback

        traceback.print_exc()
