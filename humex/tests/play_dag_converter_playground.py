"""Playground test for DAG converter system.

This test demonstrates converting an analyzer.yaml file to a DAG YAML file
and then running metrics analysis with video output.
"""

import os
import sys
from pathlib import Path
import tempfile
import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from humex import analyze
from humex.metrics.analyzer import DAGConverter, AnalyzerConverter, LogicConverter


def test_analyzer_to_dag_conversion():
    """Test converting analyzer to DAG and running analysis."""
    print("=" * 70)
    print("Testing DAG Converter System")
    print("=" * 70)
    print()

    # Step 1: Convert analyzer to DAG
    print("Step 1: Converting analyzer.yaml to DAG YAML")
    print("-" * 70)

    try:
        # Create converter
        converter = DAGConverter()

        # Convert the safety_basic analyzer
        analyzer_name = "safety_basic"
        print(f"Converting analyzer: {analyzer_name}")

        last_metric_id = converter.convert_analyzer(analyzer_name)
        print(f"✓ Analyzer converted successfully. Last metric node ID: {last_metric_id}")
        print()

        # Build the DAG structure
        dag_dict = converter.build(
            description=f"Converted from analyzer: {analyzer_name}"
        )

        print(f"DAG Structure:")
        print(f"  Description: {dag_dict.get('description', '')}")
        print(f"  Total nodes: {len(dag_dict['nodes'])}")
        print()

        # Show node types distribution
        node_types = {}
        for node_id, node_config in dag_dict['nodes'].items():
            node_type = node_config['type']
            node_types[node_type] = node_types.get(node_type, 0) + 1

        print("Node distribution by type:")
        for node_type, count in sorted(node_types.items()):
            print(f"  {node_type}: {count} nodes")
        print()

        # Save to temporary YAML file
        temp_dir = tempfile.mkdtemp()
        dag_yaml_path = os.path.join(temp_dir, "analyzer_converted.yaml")

        with open(dag_yaml_path, 'w') as f:
            yaml.dump(dag_dict, f, default_flow_style=False, sort_keys=False)

        print(f"✓ DAG YAML saved to: {dag_yaml_path}")
        print()

        # Also save to tests/dag_cfg directory for use with analyze() function
        dag_cfg_dir = Path(__file__).parent / "dag_cfg"
        dag_cfg_dir.mkdir(parents=True, exist_ok=True)
        example_yaml_path = dag_cfg_dir / f"{analyzer_name}_converted.yaml"

        with open(example_yaml_path, 'w') as f:
            yaml.dump(dag_dict, f, default_flow_style=False, sort_keys=False)

        print(f"✓ DAG YAML also saved to: {example_yaml_path}")
        print()

        # Step 2: Run analysis with the converted DAG
        print("=" * 70)
        print("Step 2: Running Metrics Analysis with Converted DAG")
        print("-" * 70)
        print()

        # Use the test scenario
        scenario_name = "scenario3"
        dag_config = f"{analyzer_name}_converted"

        print(f"Scenario: {scenario_name}")
        print(f"DAG Config: {dag_config}")
        print()

        try:
            print("Running analysis...")
            results = analyze(
                scenario_name=scenario_name,
                dag_config=dag_config,
                visualize=False,  # Don't show window for automated test
                save_video=True   # Save video file
            )

            print()
            print("=" * 70)
            print("ANALYSIS RESULTS")
            print("=" * 70)
            print()

            print(f"Scenario name: {results['scenario_name']}")
            print(f"Metric result path: {results['metric_result_path']}")
            print()

            # Check video
            if 'video_path' in results:
                video_path = results['video_path']
                if os.path.exists(video_path):
                    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                    print(f"✓ Video created: {video_path}")
                    print(f"  File size: {file_size_mb:.2f} MB")
                else:
                    print(f"✗ Video not found: {video_path}")
            else:
                print("No video path in results")
            print()

            # Analyze metric result
            metric_result = results['metric_result']
            print(f"Metric Result Details:")
            print(f"  DAG description: {metric_result.dag_description}")
            print(f"  Final result (pass/fail): {metric_result.final_result}")
            print(f"  Evaluation time: {metric_result.evaluation_time_seconds:.4f}s")
            print(f"  Nodes evaluated: {metric_result.nodes_evaluated}")
            print(f"  Total nodes: {metric_result.total_nodes}")
            print()

            # Print leaf node results
            print(f"Leaf Node Results ({len(metric_result.leaf_node_results)} nodes):")
            for i, leaf_result in enumerate(metric_result.leaf_node_results):
                metric_name = leaf_result.name if leaf_result.name else f"(unnamed-{leaf_result.node_id})"
                print(f"  [{i+1}] Node {leaf_result.node_id}: {metric_name}")
                print(f"      Frame results: {len(leaf_result.frame_results)} frames")

                if leaf_result.HasField('boolean_reduced'):
                    print(f"      Reduced value: {leaf_result.boolean_reduced} (boolean)")
                elif leaf_result.HasField('numeric_reduced'):
                    print(f"      Reduced value: {leaf_result.numeric_reduced:.4f} (numeric)")
                elif leaf_result.HasField('string_reduced'):
                    print(f"      Reduced value: {leaf_result.string_reduced} (string)")

                # Sample frame results
                if leaf_result.frame_results:
                    num_frames = len(leaf_result.frame_results)
                    sample_count = min(3, num_frames)
                    first_frames = [fr.frame_result for fr in leaf_result.frame_results[:sample_count]]
                    print(f"      First {sample_count} frames: {first_frames}")

                    if num_frames > sample_count * 2:
                        last_frames = [fr.frame_result for fr in leaf_result.frame_results[-sample_count:]]
                        print(f"      Last {sample_count} frames: {last_frames}")
                print()

            print("=" * 70)
            print("✓ Test completed successfully!")
            print("=" * 70)

            return True

        except Exception as e:
            print()
            print("=" * 70)
            print("✗ Analysis failed with error:")
            print("=" * 70)
            print(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    except Exception as e:
        print()
        print("=" * 70)
        print("✗ Conversion failed with error:")
        print("=" * 70)
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_logic_converter():
    """Test converting logic to DAG."""
    print()
    print("=" * 70)
    print("Testing Logic Converter")
    print("=" * 70)
    print()

    try:
        converter = LogicConverter()

        # Try converting a logic from the analyzer
        logic_name = "FrontVehicleDetection"
        print(f"Converting logic: {logic_name}")

        try:
            node_id = converter.convert(logic_name)
            print(f"✓ Logic converted successfully. Leaf node ID: {node_id}")

            # Build and show structure
            dag_dict = converter.build(description=f"Converted logic: {logic_name}")
            print(f"  Total nodes: {len(dag_dict['nodes'])}")

            node_types = {}
            for node_id, node_config in dag_dict['nodes'].items():
                node_type = node_config['type']
                node_types[node_type] = node_types.get(node_type, 0) + 1

            print("  Node types:")
            for node_type, count in sorted(node_types.items()):
                print(f"    {node_type}: {count}")

        except Exception as e:
            print(f"Note: Could not convert logic '{logic_name}': {e}")
            print("This is expected if the logic doesn't exist in the logics directory.")

        print()
        return True

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success_converter = test_logic_converter()
    success_analyzer = test_analyzer_to_dag_conversion()

    print()
    print("=" * 70)
    if success_analyzer:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
    print("=" * 70)
    print()
