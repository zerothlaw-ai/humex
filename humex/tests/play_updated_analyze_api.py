"""Test script for updated analyze() API with analyzer_config and save_dag support."""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from humex import analyze


def test_analyze_with_analyzer_config():
    """Test analyze() with analyzer_config parameter."""
    print("=" * 70)
    print("Test 1: Analyze with analyzer_config (auto-convert to DAG)")
    print("=" * 70)
    print()

    scenario_name = "scenario3"
    analyzer_name = "safety_basic"

    try:
        print(f"Analyzing scenario '{scenario_name}' with analyzer '{analyzer_name}'")
        print()

        results = analyze(
            scenario_name=scenario_name,
            analyzer_config=analyzer_name,
            visualize=False,
            save_video=False,
            save_dag=False
        )

        print()
        print("✓ Test 1 Passed!")
        print(f"  Scenario: {results['scenario_name']}")
        print(f"  DAG Path: {results['dag_path']}")
        print(f"  DAG Result Path: {results['dag_result_path']}")
        print()
        return True

    except Exception as e:
        print()
        print(f"✗ Test 1 Failed: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


def test_analyze_with_dag_config():
    """Test analyze() with dag_config parameter (original behavior)."""
    print("=" * 70)
    print("Test 2: Analyze with dag_config (direct DAG)")
    print("=" * 70)
    print()

    scenario_name = "scenario3"
    dag_name = "simple_speed_compliance"

    try:
        print(f"Analyzing scenario '{scenario_name}' with DAG '{dag_name}'")
        print()

        results = analyze(
            scenario_name=scenario_name,
            dag_config=dag_name,
            visualize=False,
            save_video=False,
            save_dag=False
        )

        print()
        print("✓ Test 2 Passed!")
        print(f"  Scenario: {results['scenario_name']}")
        print(f"  DAG Path: {results['dag_path']}")
        print(f"  DAG Result Path: {results['dag_result_path']}")
        print()
        return True

    except Exception as e:
        print()
        print(f"✗ Test 2 Failed: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


def test_analyze_with_save_dag():
    """Test analyze() with save_dag=True to save visualization PNG."""
    print("=" * 70)
    print("Test 3: Analyze with save_dag=True (save visualization PNG)")
    print("=" * 70)
    print()

    scenario_name = "scenario3"
    analyzer_name = "safety_basic"

    try:
        print(f"Analyzing scenario '{scenario_name}' with analyzer '{analyzer_name}'")
        print(f"Will save DAG visualization as PNG")
        print()

        results = analyze(
            scenario_name=scenario_name,
            analyzer_config=analyzer_name,
            visualize=False,
            save_video=False,
            save_dag=True  # Enable DAG visualization
        )

        print()
        print("✓ Test 3 Passed!")
        print(f"  Scenario: {results['scenario_name']}")
        print(f"  DAG Path: {results['dag_path']}")
        print(f"  DAG Result Path: {results['dag_result_path']}")

        if 'dag_visualization_path' in results:
            viz_path = results['dag_visualization_path']
            if os.path.exists(viz_path):
                file_size_kb = os.path.getsize(viz_path) / 1024
                print(f"  DAG Visualization: {viz_path}")
                print(f"    File size: {file_size_kb:.1f} KB")
            else:
                print(f"  WARNING: Visualization file not found at {viz_path}")
        else:
            print(f"  No DAG visualization in results (graphviz may not be installed)")

        print()
        return True

    except Exception as e:
        print()
        print(f"✗ Test 3 Failed: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


def test_analyze_with_video_and_dag():
    """Test analyze() with both save_video and save_dag."""
    print("=" * 70)
    print("Test 4: Analyze with save_video=True and save_dag=True")
    print("=" * 70)
    print()

    scenario_name = "scenario3"
    dag_name = "simple_speed_compliance"

    try:
        print(f"Analyzing scenario '{scenario_name}' with DAG '{dag_name}'")
        print(f"Will save video and DAG visualization")
        print()

        results = analyze(
            scenario_name=scenario_name,
            dag_config=dag_name,
            visualize=False,
            save_video=True,
            save_dag=True
        )

        print()
        print("✓ Test 4 Passed!")
        print(f"  Scenario: {results['scenario_name']}")
        print(f"  DAG Path: {results['dag_path']}")
        print(f"  DAG Result Path: {results['dag_result_path']}")

        if 'video_path' in results:
            video_path = results['video_path']
            if os.path.exists(video_path):
                file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                print(f"  Video: {video_path}")
                print(f"    File size: {file_size_mb:.2f} MB")
            else:
                print(f"  WARNING: Video file not found at {video_path}")
        else:
            print(f"  No video in results")

        if 'dag_visualization_path' in results:
            viz_path = results['dag_visualization_path']
            if os.path.exists(viz_path):
                file_size_kb = os.path.getsize(viz_path) / 1024
                print(f"  DAG Visualization: {viz_path}")
                print(f"    File size: {file_size_kb:.1f} KB")
            else:
                print(f"  WARNING: Visualization file not found at {viz_path}")
        else:
            print(f"  No DAG visualization in results (graphviz may not be installed)")

        print()
        return True

    except Exception as e:
        print()
        print(f"✗ Test 4 Failed: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


def test_analyze_error_no_config():
    """Test that analyze() raises error when neither config is provided."""
    print("=" * 70)
    print("Test 5: Error handling - neither dag_config nor analyzer_config")
    print("=" * 70)
    print()

    scenario_name = "scenario3"

    try:
        print(f"Attempting to analyze scenario '{scenario_name}' without any config")
        print()

        results = analyze(
            scenario_name=scenario_name,
            visualize=False,
            save_video=False
        )

        print()
        print("✗ Test 5 Failed: Should have raised an error!")
        print()
        return False

    except Exception as e:
        error_msg = str(e)
        if "Either 'dag_config' or 'analyzer_config' must be provided" in error_msg:
            print(f"✓ Test 5 Passed!")
            print(f"  Correctly raised error: {error_msg}")
            print()
            return True
        else:
            print()
            print(f"✗ Test 5 Failed: Got different error: {error_msg}")
            print()
            return False


if __name__ == '__main__':
    print()
    print("=" * 70)
    print("Testing Updated analyze() API")
    print("=" * 70)
    print()

    results = []

    # Run tests
    results.append(test_analyze_with_analyzer_config())
    results.append(test_analyze_with_dag_config())
    results.append(test_analyze_with_save_dag())
    results.append(test_analyze_with_video_and_dag())
    results.append(test_analyze_error_no_config())

    # Summary
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("✓ All tests passed!")
    else:
        print(f"✗ {total - passed} test(s) failed")

    print("=" * 70)
    print()
