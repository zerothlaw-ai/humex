"""Analyzer metrics computation API for end-to-end metrics evaluation.

This module provides a unified interface for computing metrics from scenario data
and analyzer/logic configurations, returning protobuf metric results.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from .convert_analyzer_metrics_api import ConvertAnalyzerMetricsAPI
from ._metrics_result_utils import get_metrics_result_file_path_with_timestamp
from ..scenario_api import ScenarioAPI
from ...metrics.dag.dag import MetricDAG
from ...metrics.dag.dag_evaluator import DAGEvaluator
from ...utils.paths import get_video_file_path, ensure_scenario_folder


class ComputeAnalyzerMetricsAPI:
    """API for computing metrics end-to-end from scenario data and configs.

    This class provides a complete pipeline for metrics computation:
    1. Load scenario from proto files
    2. Convert analyzer/logic configs to DAG
    3. Evaluate DAG against scenario
    4. Return protobuf metric results

    Supports optional saving of intermediate DAG YAML and visualization.
    """

    def __init__(self):
        """Initialize with internal API instances."""
        self.converter_api = ConvertAnalyzerMetricsAPI()
        self.scenario_api = ScenarioAPI()

    def compute(
        self,
        analyzer_yaml_path: str,
        scenario_folder_path: Optional[str] = None,
        scenario_file_path: Optional[str] = None,
        map_file_path: Optional[str] = None,
        logic_yaml_paths: Optional[List[str]] = None,
        signal_file_path: Optional[str] = None,
        save_dag_yaml: bool = False,
        save_dag_visualization: bool = False,
        output_dir: Optional[str] = None,
        visualize: bool = False,
        save_video: bool = False,
        video_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute metrics for a scenario using analyzer and logic configs.

        Complete pipeline: load scenario → convert configs → evaluate → visualize (optional) → return results

        Supports two input modes (mutually exclusive):
        1. Folder mode: Provide scenario_folder_path containing scenario proto files
        2. Legacy mode: Provide scenario_file_path and map_file_path

        Args:
            analyzer_yaml_path: Path to analyzer configuration YAML file
            scenario_folder_path: Path to folder containing scenario proto files.
                                 Uses auto-discovery via ScenarioAPI.load_from_folder().
                                 Mutually exclusive with scenario_file_path/map_file_path.
            scenario_file_path: Path to scenario_data.proto file.
                               Required for legacy mode, mutually exclusive with scenario_folder_path.
            map_file_path: Path to map.proto file.
                          Required for legacy mode, mutually exclusive with scenario_folder_path.
            logic_yaml_paths: List of logic configuration YAML paths (optional)
            signal_file_path: Path to signal.proto file (optional)
            save_dag_yaml: Whether to save converted DAG YAML
            save_dag_visualization: Whether to save DAG visualization PNG
            output_dir: Directory for output files (if save_* is True).
                       If None and save_* is True, defaults to "output"
            visualize: Whether to display animation window (default: False)
            save_video: Whether to save animation as MP4 video file (default: False)
            video_path: Custom path for video file. If not provided and save_video=True,
                       auto-generates path using analyzer name (optional)

        Returns:
            Dictionary with keys:
            - 'metric_result': MetricResult protobuf object
            - 'metric_result_path': Path to saved .pb file (None if not saved)
            - 'dag_yaml_path': Path to saved DAG YAML (None if not saved)
            - 'dag_visualization_path': Path to saved visualization (None if not saved)
            - 'video_path': Path to saved video file (None if not saved)
            - 'evaluation_metadata': Dict with evaluation statistics:
              * 'evaluation_time_seconds': float
              * 'nodes_evaluated': int
              * 'total_nodes': int
              * 'final_result': bool
              * 'num_leaf_nodes': int

        Raises:
            FileNotFoundError: If any input file not found
            ValueError: If config format invalid, evaluation fails, or input mode validation fails
        """
        # Validate input modes - exactly one mode must be used
        folder_mode = scenario_folder_path is not None
        legacy_mode = scenario_file_path is not None or map_file_path is not None

        if folder_mode and legacy_mode:
            raise ValueError(
                "Cannot use both folder mode (scenario_folder_path) and legacy mode "
                "(scenario_file_path/map_file_path). Choose one input mode."
            )

        if not folder_mode and not legacy_mode:
            raise ValueError(
                "Must provide either scenario_folder_path (folder mode) or "
                "scenario_file_path and map_file_path (legacy mode)."
            )

        if legacy_mode and (scenario_file_path is None or map_file_path is None):
            raise ValueError(
                "Legacy mode requires both scenario_file_path and map_file_path."
            )
        logic_yaml_paths = logic_yaml_paths or []

        print("=" * 70)
        print("Starting Metrics Computation Pipeline")
        print("=" * 70)

        # ===== Step 1: Load scenario based on input mode =====
        print("\n[1/4] Loading scenario...")
        try:
            if folder_mode:
                # Folder mode: use ScenarioAPI.load_from_folder()
                folder_path = Path(scenario_folder_path)
                if not folder_path.exists():
                    raise FileNotFoundError(f"Scenario folder not found: {folder_path}")
                if not folder_path.is_dir():
                    raise ValueError(f"scenario_folder_path must be a directory: {folder_path}")

                print(f"Loading scenario from folder {folder_path.name}...")
                scenario = self.scenario_api.load_from_folder(
                    scenario_folder_path=str(folder_path),
                    enhance=True,  # Automatically calculate velocities/accelerations
                )
                scenario_name_from_path = folder_path.name
            else:
                # Legacy mode: use load_from_proto_files()
                print(f"Loading scenario from proto files...")
                scenario = self.scenario_api.load_from_proto_files(
                    scenario_file_path=scenario_file_path,
                    map_file_path=map_file_path,
                    signal_file_path=signal_file_path,
                    enhance=True,  # Automatically calculate velocities/accelerations
                )
                scenario_name_from_path = Path(scenario_file_path).stem

            print(
                f"✓ Scenario loaded with {len(scenario.frames)} frames, "
                f"ego_id={scenario.ego_id}"
            )
        except Exception as e:
            raise ValueError(f"Failed to load scenario: {e}")

        # ===== Step 2: Convert analyzer to DAG =====
        print("\n[2/4] Converting analyzer config to DAG...")

        analyzer_name = Path(analyzer_yaml_path).stem
        # Get scenario name for standard naming
        scenario_name = scenario.scenario_name or scenario_name_from_path

        try:
            conversion_result = self.converter_api.convert_and_save(
                analyzer_yaml_path=analyzer_yaml_path,
                logic_yaml_paths=logic_yaml_paths,
                output_path=None,  # Use standard naming convention
                save_visualization=save_dag_visualization,
                scenario_name=scenario_name if (save_dag_yaml or save_dag_visualization) else None,
            )
            print(
                f"✓ Converted to DAG with {conversion_result['num_nodes']} nodes, "
                f"{conversion_result['num_edges']} edges"
            )
        except Exception as e:
            raise ValueError(f"Failed to convert analyzer config: {e}")

        dag_yaml_path = (
            conversion_result["dag_yaml_path"] if save_dag_yaml else None
        )
        dag_visualization_path = conversion_result.get("dag_visualization_path")

        # ===== Step 3: Load DAG from YAML =====
        print("\n[3/4] Loading and evaluating DAG...")
        try:
            dag = MetricDAG()
            dag.load_from_yaml(conversion_result["dag_yaml_path"])
            print(f"✓ DAG loaded with {len(dag.nodes)} nodes")
        except Exception as e:
            raise ValueError(f"Failed to load DAG: {e}")

        # ===== Step 4: Evaluate metrics =====
        logs = []
        try:
            evaluator = DAGEvaluator(scenario, dag, logs=logs)
            evaluation_results = evaluator.evaluate()
            print(f"✓ DAG evaluation completed")
        except Exception as e:
            logs.append(f"ERROR: {str(e)}")
            err = ValueError(f"Failed to evaluate metrics: {e}")
            err.logs = logs
            raise err from e

        # ===== Step 5: Convert to protobuf =====
        print("\n[4/4] Converting to protobuf...")
        try:
            metric_result_proto = evaluator.save_to_proto(evaluation_results)
            print(f"✓ Metrics converted to protobuf")
        except Exception as e:
            raise ValueError(f"Failed to convert results to protobuf: {e}")

        # ===== Step 6: Optional: Visualize metrics =====
        video_file_path = None
        if visualize or save_video:
            print("\n[5/5] Generating visualization...")

            # Determine video file path if saving
            if save_video:
                if video_path is None:
                    video_file_path = get_video_file_path(analyzer_name)
                else:
                    video_file_path = video_path

            # Create and run visualizer
            if visualize and save_video:
                print(f"Displaying animation and saving video: {video_file_path}")
            elif visualize:
                print(f"Displaying animation (video not saved)")
            else:
                print(f"Saving video (no animation display): {video_file_path}")

            try:
                # Lazy import Visualizer to defer tkinter/matplotlib import until needed
                from ...simulator.visualizer.visualizer_3d import Visualizer

                vis = Visualizer(
                    scenario,
                    dag_result=metric_result_proto,
                    ego_id=scenario.ego_id,
                    dag_name=analyzer_name
                )
                vis.run(rtf=1, video_path=video_file_path, show=visualize)

            except ModuleNotFoundError as e:
                if 'tkinter' in str(e):
                    print(f"\nWarning: tkinter (python3-tk) not found.")
                    if visualize:
                        print(f"Cannot display interactive animation.")
                    if save_video:
                        print(f"Cannot save video (requires tkinter support).")
                    print(f"Skipping visualization and video.")
                    video_file_path = None
                else:
                    raise
            except Exception as e:
                print(f"\nWarning: Visualization failed: {e}")
                if visualize:
                    print(f"Skipping animation display.")
                if save_video:
                    print(f"Skipping video save.")
                video_file_path = None

        # ===== Step 7: Optional: Save protobuf result =====
        metric_result_path = None
        if save_dag_yaml:
            metric_result_path = get_metrics_result_file_path_with_timestamp(scenario_name, analyzer_name)
            try:
                with open(metric_result_path, "wb") as f:
                    f.write(metric_result_proto.SerializeToString())
                print(f"✓ Saved metric result protobuf: {metric_result_path}")
            except Exception as e:
                print(f"Warning: Failed to save metric result protobuf: {e}")
                metric_result_path = None

        # ===== Step 7: Prepare evaluation metadata =====
        metadata_dict = evaluation_results.get("metadata", {})
        evaluation_metadata = {
            "evaluation_time_seconds": metadata_dict.get("evaluation_time_seconds", 0.0),
            "nodes_evaluated": metadata_dict.get("nodes_evaluated", 0),
            "total_nodes": metadata_dict.get("total_nodes", 0),
            "final_result": evaluation_results.get("final_result"),
            "num_leaf_nodes": len(evaluation_results.get("leaf_nodes", [])),
        }

        # ===== Step 8: Return results =====
        print("\n" + "=" * 70)
        print(f"Metrics Computation Completed Successfully")
        print("=" * 70)
        print(f"\nResults Summary:")
        print(f"  Final Result: {evaluation_metadata['final_result']}")
        print(f"  Evaluation Time: {evaluation_metadata['evaluation_time_seconds']:.3f}s")
        print(
            f"  Nodes Evaluated: {evaluation_metadata['nodes_evaluated']}/{evaluation_metadata['total_nodes']}"
        )
        print(f"  Leaf Nodes: {evaluation_metadata['num_leaf_nodes']}")

        return {
            "metric_result": metric_result_proto,
            "metric_result_path": metric_result_path,
            "dag_yaml_path": dag_yaml_path,
            "dag_visualization_path": dag_visualization_path,
            "video_path": video_file_path if save_video else None,
            "evaluation_metadata": evaluation_metadata,
            "logs": logs,
        }
