"""Simulation API with DAG metrics computation.

This module provides the RunSimulationWithDagMetricsAPI class that combines
simulation execution with DAG-based metrics computation.
"""

from typing import Dict, Optional, Any, TYPE_CHECKING

from .run_simulation_api import RunSimulationAPI
from ..metrics_api import ComputeDagMetricsAPI

if TYPE_CHECKING:
    from humex.proto import metric_result_pb2


class RunSimulationWithDagMetricsAPI:
    """API for running simulations and computing DAG-based metrics.

    This API combines RunSimulationAPI with ComputeDagMetricsAPI to provide
    a complete pipeline: run simulation → compute metrics from DAG YAML.
    """

    def __init__(self):
        """Initialize with internal API instances."""
        self.simulation_api = RunSimulationAPI()
        self.metrics_api = ComputeDagMetricsAPI()

    def run(
        self,
        config_path: str,
        map_path: str,
        dag_yaml_path: str,
        output_dir: Optional[str] = None,
        output_name: Optional[str] = None,
        visualize: bool = False,
        save_video: bool = False,
        video_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run simulation and compute DAG-based metrics.

        Args:
            config_path: Path to JSON scenario configuration file
            map_path: Path to map protobuf file (.pb)
            dag_yaml_path: Path to pre-existing DAG YAML configuration file
            output_dir: Output directory (default: data/scenarios/{name}/)
            output_name: Output name (default: derived from config)
            visualize: Whether to display animation window (default: False)
            save_video: Whether to save animation as MP4 video (default: False)
            video_path: Custom path for video file (optional)

        Returns:
            dict with keys:
                - 'scenario_proto_path': Path to generated scenario .pb file
                - 'scenario': Scenario object
                - 'simulation_time_seconds': Simulation execution time
                - 'metric_result': MetricResult protobuf
                - 'evaluation_metadata': Dict with evaluation statistics
                - 'video_path': Path to saved video (None if not saved)
        """
        # Step 1: Run simulation
        sim_result = self.simulation_api.run(
            config_path=config_path,
            map_path=map_path,
            output_dir=output_dir,
            output_name=output_name,
        )

        # Step 2: Compute metrics using DAG YAML
        print(f"\nComputing metrics using DAG: {dag_yaml_path}")
        metrics_result = self.metrics_api.compute(
            dag_yaml_path=dag_yaml_path,
            scenario_file_path=sim_result['scenario_proto_path'],
            map_file_path=map_path,
            save_metrics_result=False,
            visualize=visualize,
            save_video=save_video,
            video_path=video_path,
        )

        # Step 3: Combine results
        return {
            'scenario_proto_path': sim_result['scenario_proto_path'],
            'scenario': sim_result['scenario'],
            'simulation_time_seconds': sim_result['simulation_time_seconds'],
            'metric_result': metrics_result['metric_result'],
            'evaluation_metadata': metrics_result['evaluation_metadata'],
            'video_path': metrics_result.get('video_path'),
        }
