"""Simulation API for running autonomous vehicle simulations.

This module provides APIs for running simulations from JSON config and map files:
- RunSimulationAPI: Pure simulation only
- RunSimulationWithDagMetricsAPI: Simulation + DAG-based metrics

The analyzer-based variant (``RunSimulationWithAnalyzerMetricsAPI``) is retired
from the public surface; use the DAG variant instead. Its module remains on disk.
"""

from .run_simulation_api import RunSimulationAPI
from .run_simulation_with_dag_metrics_api import RunSimulationWithDagMetricsAPI

__all__ = [
    "RunSimulationAPI",
    "RunSimulationWithDagMetricsAPI",
]
