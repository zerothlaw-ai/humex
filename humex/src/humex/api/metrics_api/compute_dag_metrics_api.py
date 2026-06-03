"""API for computing metrics from DAG YAML configurations.

This module provides the ComputeDagMetricsAPI class which takes a DAG YAML file
and scenario data, evaluates the DAG using the metric evaluation system, and
returns the computed metrics results.

Usage:
    >>> from humex.api import ComputeDagMetricsAPI
    >>> api = ComputeDagMetricsAPI()
    >>> result = api.compute(
    ...     dag_yaml_path="data/dag_cfg/my_dag.yaml",
    ...     scenario_file_path="data/scenarios/scenario_001/ava_scenario.proto",
    ...     map_file_path="data/scenarios/scenario_001/ava_map.proto",
    ...     save_metrics_result=True
    ... )
    >>> print(result['metric_result'])
"""

from pathlib import Path
from typing import Optional, Dict, Any

from humex.api.scenario_api import ScenarioAPI
from humex.metrics.dag.dag import MetricDAG
from humex.metrics.dag.dag_evaluator import DAGEvaluator
from ._metrics_result_utils import get_metrics_result_file_path_with_timestamp


class ComputeDagMetricsAPI:
    """API for computing metrics from DAG YAML configurations.

    Takes a DAG YAML file and scenario data, evaluates using DAGEvaluator,
    and returns metrics results. Used when you already have a DAG configuration
    (from translate_metrics, manual creation, or conversion from analyzer).

    The core metric evaluation is performed by DAGEvaluator, which is also used
    by ComputeAnalyzerMetricsAPI (after converting analyzer YAML to DAG).
    """

    def __init__(self):
        """Initialize API with required dependencies.

        Raises:
            ImportError: If ScenarioAPI cannot be imported
        """
        self.scenario_api = ScenarioAPI()

    def compute(
        self,
        dag_yaml_path: str,
        scenario_folder_path: Optional[str] = None,
        scenario_file_path: Optional[str] = None,
        map_file_path: Optional[str] = None,
        signal_file_path: Optional[str] = None,
        save_metrics_result: bool = False,
        visualize: bool = False,
        save_video: bool = False,
        video_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute metrics for a scenario using a DAG YAML configuration.

        Loads a scenario from proto files or a folder, loads a DAG from YAML,
        evaluates the DAG against the scenario using DAGEvaluator, and returns the computed metrics.

        Supports two input modes (mutually exclusive):
        1. Folder mode: Provide scenario_folder_path containing scenario proto files
        2. Legacy mode: Provide scenario_file_path and map_file_path

        Args:
            dag_yaml_path: Path to DAG YAML configuration file. Should be a valid
                          DAG YAML with nodes and structure (e.g., from translate_metrics
                          or data/dag_cfg folder).
            scenario_folder_path: Path to folder containing scenario proto files.
                                 Uses auto-discovery via ScenarioAPI.load_from_folder().
                                 Mutually exclusive with scenario_file_path/map_file_path.
            scenario_file_path: Path to scenario_data.proto file containing scenario data.
                               Required for legacy mode, mutually exclusive with scenario_folder_path.
            map_file_path: Path to map file (either map.proto or map.json format).
                          Required for legacy mode, mutually exclusive with scenario_folder_path.
            signal_file_path: Optional path to signal.proto file for signal data
            save_metrics_result: Whether to save metrics result as protobuf file
                                (saved to data/scenarios/{dag_name}/ava_metrics_result_{dag_name}.proto)
            visualize: Whether to display interactive 3D visualization of scenario
                      with metrics overlay
            save_video: Whether to save visualization as MP4 video file
            video_path: Optional custom path for video file. If not provided and
                       save_video=True, uses default location

        Returns:
            Dictionary with keys:
            - 'metric_result': MetricResult protobuf object containing all computed metrics
            - 'metric_result_path': str | None - Path to saved protobuf file (None if not saved)
            - 'dag_yaml_path': str - The input DAG YAML path
            - 'evaluation_metadata': dict - Statistics including:
                - 'evaluation_time_seconds': float
                - 'nodes_evaluated': int
                - 'total_nodes': int
                - 'final_result': bool | None
                - 'num_leaf_nodes': int
            - 'video_path': str | None - Path to saved video (None if not saved)

        Raises:
            FileNotFoundError: If DAG YAML path or scenario files don't exist
            ValueError: If DAG YAML is invalid, cannot be loaded, or input mode validation fails
            Exception: If evaluation fails or other system errors occur

        Example:
            >>> api = ComputeDagMetricsAPI()
            >>> # Folder mode
            >>> result = api.compute(
            ...     dag_yaml_path="data/dag_cfg/speed_check.yaml",
            ...     scenario_folder_path="/path/to/scenario_folder",
            ... )
            >>> # Legacy mode
            >>> result = api.compute(
            ...     dag_yaml_path="data/dag_cfg/speed_check.yaml",
            ...     scenario_file_path="data/scenarios/test_001/ava_scenario.proto",
            ...     map_file_path="data/scenarios/test_001/ava_map.proto",
            ...     save_metrics_result=True,
            ...     visualize=False
            ... )
            >>> print(f"Metrics computed in {result['evaluation_metadata']['evaluation_time_seconds']:.2f}s")
            >>> print(f"Result: {result['metric_result'].final_result}")
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
        # 1. Validate DAG YAML path
        dag_yaml_path = Path(dag_yaml_path)
        if not dag_yaml_path.exists():
            raise FileNotFoundError(f"DAG YAML file not found: {dag_yaml_path}")

        # 2. Load scenario based on input mode
        if folder_mode:
            # Folder mode: use ScenarioAPI.load_from_folder()
            scenario_folder_path = Path(scenario_folder_path)
            if not scenario_folder_path.exists():
                raise FileNotFoundError(f"Scenario folder not found: {scenario_folder_path}")
            if not scenario_folder_path.is_dir():
                raise ValueError(f"scenario_folder_path must be a directory: {scenario_folder_path}")

            print(f"Loading scenario from folder {scenario_folder_path.name}...")
            scenario = self.scenario_api.load_from_folder(
                scenario_folder_path=str(scenario_folder_path),
                enhance=True  # Calculate velocities and accelerations
            )
            scenario_name = scenario_folder_path.name
        else:
            # Legacy mode: use load_from_proto_files()
            scenario_file_path = Path(scenario_file_path)
            if not scenario_file_path.exists():
                raise FileNotFoundError(f"Scenario file not found: {scenario_file_path}")

            map_file_path = Path(map_file_path)
            if not map_file_path.exists():
                raise FileNotFoundError(f"Map file not found: {map_file_path}")

            print(f"Loading scenario from {scenario_file_path.name}...")
            scenario = self.scenario_api.load_from_proto_files(
                scenario_file_path=str(scenario_file_path),
                map_file_path=str(map_file_path),
                signal_file_path=signal_file_path,
                enhance=True  # Calculate velocities and accelerations
            )
            scenario_name = scenario_file_path.stem

        print(f"Scenario loaded: {len(scenario.frames)} frames")

        # 3. Load DAG from YAML
        print(f"Loading DAG from {dag_yaml_path.name}...")
        dag = MetricDAG()
        try:
            dag.load_from_yaml(str(dag_yaml_path))
        except Exception as e:
            raise ValueError(f"Failed to load DAG from {dag_yaml_path}: {str(e)}")
        print(f"DAG loaded: {len(dag.nodes)} nodes")

        # 4. Evaluate DAG using DAGEvaluator
        logs = []
        print("Evaluating DAG...")
        evaluator = DAGEvaluator(scenario, dag, logs=logs)
        try:
            evaluation_results = evaluator.evaluate()
        except Exception as e:
            logs.append(f"ERROR: {str(e)}")
            err = ValueError(str(e))
            err.logs = logs
            raise err from e

        # 5. Convert evaluation results to protobuf
        metric_result_proto = evaluator.save_to_proto(evaluation_results)

        # 6. Optional: Save metrics result protobuf
        metric_result_path = None
        if save_metrics_result:
            dag_name = dag_yaml_path.stem
            # scenario_name was set during scenario loading (folder name or file stem)
            metric_result_path = get_metrics_result_file_path_with_timestamp(scenario_name, dag_name)

            try:
                with open(metric_result_path, "wb") as f:
                    f.write(metric_result_proto.SerializeToString())
                print(f"Metrics result saved to {metric_result_path}")
            except Exception as e:
                print(f"Warning: Failed to save metrics result: {str(e)}")
                metric_result_path = None

        # 7. Optional: Visualize and save video
        video_path_saved = None
        if visualize or save_video:
            try:
                from humex.simulator.visualizer.visualizer_3d import Visualizer

                dag_name = dag_yaml_path.stem
                print("Initializing 3D visualization...")
                vis = Visualizer(
                    scenario,
                    dag_result=metric_result_proto,
                    ego_id=scenario.ego_id,
                    dag_name=dag_name,
                )
                print("Running visualization...")
                video_path_saved = vis.run(rtf=1, video_path=video_path, show=visualize)
                if video_path_saved:
                    print(f"Video saved to {video_path_saved}")
            except ImportError:
                print("Warning: 3D visualizer not available, skipping visualization")
            except Exception as e:
                print(f"Warning: Failed to create visualization: {str(e)}")

        # 8. Return results
        return {
            "metric_result": metric_result_proto,
            "metric_result_path": str(metric_result_path) if metric_result_path else None,
            "dag_yaml_path": str(dag_yaml_path),
            "evaluation_metadata": evaluation_results.get("metadata", {}),
            "video_path": video_path_saved,
            "logs": logs,
        }
