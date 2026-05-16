"""DAG visualization API for generating PNG images from DAG YAML files.

This module provides an interface to visualize Directed Acyclic Graph (DAG)
configurations as PNG/SVG/PDF images and save them alongside the input YAML files.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any

from ...metrics.dag.dag import MetricDAG
from ...metrics.dag.dag_visualizer import visualize_dag


class VisualizeDagAPI:
    """API for generating visualizations of DAG YAML configurations.

    This class converts DAG YAML files into visual representations (PNG/SVG/PDF)
    and saves them in the same location as the input YAML file with matching
    base names. Leverages the underlying dag_visualizer functionality.
    """

    def visualize(
        self,
        dag_yaml_path: str,
        output_format: str = "png",
        scenario_name: Optional[str] = None,
        view: bool = False
    ) -> Dict[str, Any]:
        """Generate visualization of a DAG YAML file and save as image.

        Reads a DAG YAML configuration file, parses it into a MetricDAG object,
        and generates a visual representation. The image is saved in the same
        directory as the input YAML file with the same base name but with the
        appropriate image extension.

        Args:
            dag_yaml_path: Path to the DAG YAML configuration file.
                          Example: "data/scenarios/scenario4/ava_dag_scenario4.yaml"
            output_format: Image format to generate. Options: "png", "svg", "pdf".
                          Default: "png"
            scenario_name: Optional scenario name. If not provided, extracted from
                          the YAML filename using the naming convention
                          "ava_dag_{scenario_name}.yaml"
            view: Whether to open the generated image in the default viewer.
                 Default: False

        Returns:
            Dictionary with visualization metadata:
            - 'dag_visualization_path': str - Path to generated image file
            - 'dag_yaml_path': str - Path to input YAML file
            - 'num_nodes': int - Number of nodes in the DAG
            - 'num_edges': int - Number of edges in the DAG
            - 'output_format': str - Format of generated image ('png', 'svg', or 'pdf')
            - 'scenario_name': str - Extracted or provided scenario name

        Raises:
            FileNotFoundError: If the DAG YAML file does not exist
            ValueError: If the YAML file is invalid or cannot be parsed
            ValueError: If output_format is not in ['png', 'svg', 'pdf']
            ImportError: If graphviz package is not installed
            RuntimeError: If Graphviz executable is not found on system

        Example:
            >>> api = VisualizeDagAPI()
            >>> result = api.visualize("data/scenarios/scenario4/ava_dag_scenario4.yaml")
            >>> print(result['dag_visualization_path'])
            data/scenarios/scenario4/ava_dag_scenario4.png
        """
        # Validate output format
        if output_format not in ["png", "svg", "pdf"]:
            raise ValueError(
                f"Unsupported output format: {output_format}. "
                f"Supported formats: 'png', 'svg', 'pdf'"
            )

        # Extract scenario name if not provided
        if scenario_name is None:
            yaml_filename = Path(dag_yaml_path).stem
            # Expected format: ava_dag_{scenario_name}
            if yaml_filename.startswith("ava_dag_"):
                scenario_name = yaml_filename[8:]  # Remove "ava_dag_" prefix
            else:
                scenario_name = yaml_filename

        # Load DAG from YAML file
        try:
            dag = MetricDAG()
            dag.load_from_yaml(dag_yaml_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"DAG YAML file not found: {dag_yaml_path}")
        except Exception as e:
            raise ValueError(
                f"Failed to load DAG from YAML: {str(e)}"
            )

        # Calculate output path: same directory as input YAML, matching base name
        dag_yaml_dir = Path(dag_yaml_path).parent
        dag_yaml_stem = Path(dag_yaml_path).stem
        output_path_no_ext = str(dag_yaml_dir / dag_yaml_stem)

        # Generate visualization using dag_visualizer
        try:
            visualization_path = visualize_dag(
                dag,
                output_format=output_format,
                output_path=output_path_no_ext,
                view=view,
                title=f"DAG: {scenario_name}"
            )
        except ImportError:
            raise ImportError(
                "graphviz package is not installed. "
                "Install with: pip install graphviz"
            )
        except RuntimeError as e:
            raise RuntimeError(
                f"Graphviz executable not found or visualization failed: {str(e)}"
            )

        # Calculate number of nodes and edges
        num_nodes = len(dag.nodes)
        num_edges = len(list(dag.graph.edges()))

        return {
            "dag_visualization_path": visualization_path,
            "dag_yaml_path": dag_yaml_path,
            "num_nodes": num_nodes,
            "num_edges": num_edges,
            "output_format": output_format,
            "scenario_name": scenario_name
        }
