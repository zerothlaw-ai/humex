"""
Playground script for testing humex metrics computation APIs.

Demonstrates how to use the new ComputeAnalyzerMetricsAPI to compute metrics
from scenario data and analyzer/logic configurations.
"""

from humex.api.core_apis import ComputeAnalyzerMetricsAPI
import os


if __name__ == "__main__":
    # =========================================================================
    # Configuration
    # =========================================================================
    print("=" * 70)
    print("humex Metrics Computation Playground")
    print("=" * 70)
    print()

    # Scenario to analyze (using hume-craft generated scenario)
    scenario_name = "hume_craft_test"

    # File paths for scenario data (relative to project root)
    scenario_file_path = f"../data/scenarios/{scenario_name}/ava_scenario_{scenario_name}.pb"
    # Map file is from scenario3 (same map used for hume-craft)
    map_file_path = "../data/scenarios/scenario3/ava_map_scenario3.pb"
    signal_file_path = "../data/scenarios/scenario3/ava_signal_scenario3.pb"

    # Analyzer configuration (relative to project root)
    analyzer_yaml_path = "../data/analyzer_cfg/safety_basic_ai.yaml"

    # Optional: Logic configuration files (empty list if none)
    logic_yaml_paths = []

    # Note: output_dir is no longer needed - results are saved to data/scenarios/{scenario_name}/ automatically

    # =========================================================================
    # Verify Input Files Exist
    # =========================================================================
    print("Verifying input files...")

    input_files = {
        "Scenario": scenario_file_path,
        "Map": map_file_path,
        "Analyzer config": analyzer_yaml_path,
    }

    # Check signal file if it exists
    if os.path.exists(signal_file_path):
        input_files["Signal"] = signal_file_path

    missing_files = []
    for name, path in input_files.items():
        if os.path.exists(path):
            print(f"✓ {name}: {path}")
        else:
            print(f"✗ {name} NOT FOUND: {path}")
            missing_files.append((name, path))

    if missing_files:
        print()
        print("=" * 70)
        print("✗ Error: Missing required files")
        print("=" * 70)
        for name, path in missing_files:
            print(f"  {name}: {path}")
        print()
        exit(1)

    print()

    # =========================================================================
    # Run Metrics Computation
    # =========================================================================
    print("=" * 70)
    print("Computing Metrics")
    print("=" * 70)
    print()

    try:
        # Initialize the metrics computation API
        compute_api = ComputeAnalyzerMetricsAPI()

        # Compute metrics
        results = compute_api.compute(
            scenario_file_path=scenario_file_path,
            map_file_path=map_file_path,
            signal_file_path=signal_file_path,
            analyzer_yaml_path=analyzer_yaml_path,
            logic_yaml_paths=logic_yaml_paths if logic_yaml_paths else None,
            save_dag_yaml=True,           # Save converted DAG YAML and metrics result
            save_dag_visualization=True,  # Save DAG visualization PNG
            visualize=True,               # Display animation window
            save_video=False,             # Don't save video file
        )

        # =====================================================================
        # Display Results
        # =====================================================================
        print()
        print("=" * 70)
        print("RESULTS")
        print("=" * 70)
        print()

        # Metric result protobuf
        metric_result = results["metric_result"]
        print(f"Scenario: {scenario_name}")
        print(f"Analyzer config: {os.path.basename(analyzer_yaml_path)}")
        print()

        # Evaluation metadata
        metadata = results["evaluation_metadata"]
        print(f"Final Result: {metric_result.final_result}")
        print(f"Evaluation Time: {metric_result.evaluation_time_seconds:.3f}s")
        print(f"Nodes Evaluated: {metadata['nodes_evaluated']}/{metadata['total_nodes']}")
        print(f"Leaf Nodes: {metadata['num_leaf_nodes']}")
        print()

        # Output file paths
        print("Output Files:")
        if results["metric_result_path"]:
            print(f"✓ Metric Result: {results['metric_result_path']}")
            if os.path.exists(results["metric_result_path"]):
                file_size_kb = os.path.getsize(results["metric_result_path"]) / 1024
                print(f"  File size: {file_size_kb:.2f} KB")
        else:
            print("✗ Metric result not saved")

        if results["dag_yaml_path"]:
            print(f"✓ DAG YAML: {results['dag_yaml_path']}")
        else:
            print("✗ DAG YAML not saved")

        if results["dag_visualization_path"]:
            print(f"✓ DAG Visualization: {results['dag_visualization_path']}")
            if os.path.exists(results["dag_visualization_path"]):
                file_size_kb = (
                    os.path.getsize(results["dag_visualization_path"]) / 1024
                )
                print(f"  File size: {file_size_kb:.2f} KB")
        else:
            print("✗ DAG visualization not saved")

        print()

        # =====================================================================
        # Display Metric Details
        # =====================================================================
        print("=" * 70)
        print("METRIC DETAILS")
        print("=" * 70)
        print()

        print(f"DAG Description: {metric_result.dag_description}")
        print(f"Evaluation Timestamp: {metric_result.evaluation_timestamp} ns")
        print()

        if metric_result.leaf_node_results:
            print(f"Leaf Node Results ({len(metric_result.leaf_node_results)} nodes):")
            for leaf_result in metric_result.leaf_node_results:
                print(f"  • {leaf_result.name} (node_id={leaf_result.node_id})")
                print(f"    Result: {leaf_result.reduced_result}")
                print(f"    Frames evaluated: {len(leaf_result.frame_results)}")
                if leaf_result.source_monitor_ids:
                    print(f"    Source monitors: {list(leaf_result.source_monitor_ids)}")
        else:
            print("No leaf node results")

        print()

    except FileNotFoundError as e:
        print()
        print("=" * 70)
        print("✗ File Not Found Error:")
        print("=" * 70)
        print(f"Error: {str(e)}")
        print()
        import traceback

        traceback.print_exc()

    except ValueError as e:
        print()
        print("=" * 70)
        print("✗ Validation Error:")
        print("=" * 70)
        print(f"Error: {str(e)}")
        print()
        import traceback

        traceback.print_exc()

    except Exception as e:
        print()
        print("=" * 70)
        print("✗ Test failed with error:")
        print("=" * 70)
        print(f"Error: {str(e)}")
        print()
        import traceback

        traceback.print_exc()

    print()
    print("=" * 70)
    print("Playground Test Complete")
    print("=" * 70)
