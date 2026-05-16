"""Metric Computation DAG Framework.

This module provides tools for defining and executing Directed Acyclic Graphs (DAGs)
of metric computation, along with visualization capabilities.

Classes:
    - MetricDAG: Main DAG execution engine with load_from_yaml() and visualize() methods
    - DagNode: Node definition dataclass

Usage:
    >>> dag = MetricDAG()
    >>> dag.load_from_yaml('path/to/dag.yaml')
    >>> dag.visualize(output_format='png', view=True)

Advanced Functions (for direct use):
    - visualize_dag: Visualize a MetricDAG instance
    - dag_to_dot: Convert MetricDAG to Graphviz DOT format
"""

from humex.metrics.dag.dag import MetricDAG
from humex.metrics.dag.dag_node import DagNode
from humex.metrics.dag.dag_visualizer import (
    visualize_dag,
    dag_to_dot,
)

__all__ = [
    # Core DAG classes
    'MetricDAG',
    'DagNode',
    # Advanced visualization functions
    'visualize_dag',
    'dag_to_dot',
]
