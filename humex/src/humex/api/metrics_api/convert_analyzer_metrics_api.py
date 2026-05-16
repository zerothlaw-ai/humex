"""Analyzer metrics conversion API for converting YAML configs to DAG format.

This module provides a unified interface for converting analyzer and logic YAML
configurations into a single DAG YAML configuration, with optional visualization.
"""

import os
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any

from ...metrics.analyzer import DAGConverter
from ...metrics.dag.dag import MetricDAG
from ...metrics.dag.dag_visualizer import visualize_dag
from ...utils.paths import get_dag_yaml_file_path, DATA_PATH


class ConvertAnalyzerMetricsAPI:
    """API for converting analyzer and logic configs to DAG YAML format.

    This class converts analyzer and logic YAML configurations into a unified
    Directed Acyclic Graph (DAG) format that can be evaluated to compute metrics.
    Supports optional DAG visualization as PNG/SVG/PDF.
    """

    def convert_and_save(
        self,
        analyzer_yaml_path: str,
        logic_yaml_paths: Optional[List[str]] = None,
        output_path: Optional[str] = None,
        save_visualization: bool = False,
        visualization_format: str = "png",
        scenario_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Convert analyzer and logic configs to DAG YAML and optionally save visualization.

        Args:
            analyzer_yaml_path: Path to analyzer configuration YAML file
            logic_yaml_paths: List of paths to logic configuration YAML files (optional).
                             If None, only the analyzer is converted.
            output_path: Path to save DAG YAML (without extension).
                        If None and scenario_name provided, saves to data/scenarios/{scenario_name}/ava_dag_{scenario_name}.yaml
                        If None and no scenario_name, saves to data/{analyzer_name}_converted.yaml
            save_visualization: Whether to save DAG visualization as image
            visualization_format: Image format: 'png', 'svg', or 'pdf'
            scenario_name: Optional scenario name for standard naming convention

        Returns:
            Dictionary with keys:
            - 'dag_yaml_path': Path to saved DAG YAML file
            - 'dag_visualization_path': Path to saved visualization (None if not saved)
            - 'dag_description': Human-readable description of the DAG
            - 'num_nodes': Total number of nodes in DAG
            - 'num_edges': Total number of edges in DAG
            - 'analyzer_name': Name of the analyzer config
            - 'logic_names': List of logic config names

        Raises:
            FileNotFoundError: If any input YAML file not found
            ValueError: If YAML format invalid or conversion fails
        """
        logic_yaml_paths = logic_yaml_paths or []

        # 1. Validate all input files exist
        if not Path(analyzer_yaml_path).exists():
            raise FileNotFoundError(f"Analyzer YAML not found: {analyzer_yaml_path}")

        for logic_path in logic_yaml_paths:
            if not Path(logic_path).exists():
                raise FileNotFoundError(f"Logic YAML not found: {logic_path}")

        # Extract names for description
        analyzer_name = Path(analyzer_yaml_path).stem
        logic_names = [Path(p).stem for p in logic_yaml_paths]

        print(f"Converting analyzer: {analyzer_name}")
        if logic_names:
            print(f"Including logics: {', '.join(logic_names)}")

        # 2. Extract directories from paths for converter
        analyzer_dir = str(Path(analyzer_yaml_path).parent)

        # Collect unique logic directories
        logic_dirs = list(set(str(Path(p).parent) for p in logic_yaml_paths)) if logic_yaml_paths else None
        # For now, use the first logic directory if multiple are provided
        logic_dir = logic_dirs[0] if logic_dirs else None

        # Create converter with proper directories
        converter = DAGConverter(logic_dir=logic_dir, analyzer_dir=analyzer_dir)

        # Convert each logic first
        for logic_path in logic_yaml_paths:
            logic_name = Path(logic_path).stem
            print(f"Converting logic: {logic_name}")
            try:
                converter.convert_logic(logic_name)
            except Exception as e:
                raise ValueError(f"Failed to convert logic '{logic_name}': {e}")

        # Convert analyzer
        try:
            converter.convert_analyzer(analyzer_name)
        except Exception as e:
            raise ValueError(f"Failed to convert analyzer '{analyzer_name}': {e}")

        # 3. Build DAG dictionary
        description = f"Converted from analyzer: {analyzer_name}"
        if logic_names:
            description += f", logics: {', '.join(logic_names)}"

        print(f"Building DAG...")
        try:
            dag_dict = converter.build(description=description)
        except Exception as e:
            raise ValueError(f"Failed to build DAG: {e}")

        # 4. Determine output path
        if output_path is None:
            if scenario_name:
                # Use standard naming convention for scenarios
                dag_yaml_path = get_dag_yaml_file_path(scenario_name)
                output_path = str(Path(dag_yaml_path).with_suffix(""))
            else:
                # Fallback for non-scenario usage
                output_path = f"{DATA_PATH}{analyzer_name}_converted"
                dag_yaml_path = f"{output_path}.yaml"
        else:
            # Remove extension if provided
            output_path = str(Path(output_path).with_suffix(""))
            dag_yaml_path = f"{output_path}.yaml"

        # Ensure output directory exists
        output_dir = os.path.dirname(dag_yaml_path) or "."
        os.makedirs(output_dir, exist_ok=True)

        # 5. Save DAG YAML
        try:
            with open(dag_yaml_path, "w") as f:
                yaml.dump(dag_dict, f, default_flow_style=False, sort_keys=False)
            print(f"Saved DAG YAML to: {dag_yaml_path}")
        except Exception as e:
            raise ValueError(f"Failed to save DAG YAML: {e}")

        # 6. Optional: Save visualization
        dag_visualization_path = None
        if save_visualization:
            dag_visualization_path = self._save_visualization(
                dag_yaml_path=dag_yaml_path,
                output_path=output_path,
                analyzer_name=analyzer_name,
                visualization_format=visualization_format
            )

        # 7. Return results with metadata
        num_nodes = len(dag_dict.get("nodes", {}))
        num_edges = sum(
            len(node.get("inputs", []))
            for node in dag_dict.get("nodes", {}).values()
        )

        return {
            "dag_yaml_path": dag_yaml_path,
            "dag_visualization_path": dag_visualization_path,
            "dag_description": description,
            "num_nodes": num_nodes,
            "num_edges": num_edges,
            "analyzer_name": analyzer_name,
            "logic_names": logic_names,
        }

    def _save_visualization(
        self,
        dag_yaml_path: str,
        output_path: str,
        analyzer_name: str,
        visualization_format: str = "png"
    ) -> Optional[str]:
        """Save DAG visualization as image file.

        Args:
            dag_yaml_path: Path to saved DAG YAML
            output_path: Base output path (without extension)
            analyzer_name: Name for visualization title
            visualization_format: Image format ('png', 'svg', 'pdf')

        Returns:
            Path to saved visualization file, or None if failed
        """
        try:
            print(f"Loading DAG for visualization...")
            dag = MetricDAG()
            dag.load_from_yaml(dag_yaml_path)

            print(f"Generating DAG visualization ({visualization_format})...")
            actual_path = visualize_dag(
                dag,
                output_format=visualization_format,
                output_path=output_path,
                view=False,
                title=f"DAG: {analyzer_name}",
            )
            print(f"Saved DAG visualization to: {actual_path}")
            return actual_path

        except ImportError as e:
            print(f"Warning: Could not save visualization - {e}")
            print(f"Install graphviz package to enable DAG visualization")
            return None
        except Exception as e:
            print(f"Warning: Failed to save visualization: {e}")
            return None
