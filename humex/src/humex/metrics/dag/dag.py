# humex/metrics/dag.py
import networkx as nx
import yaml
from pathlib import Path
from typing import Optional
from humex.metrics.dag.dag_node import DagNode


class MetricDAG:
    def __init__(self):
        self.nodes = {}
        self.graph = nx.DiGraph()
        self.metadata = {}  # Stores DAG metadata (description, source file, etc.)

    def add_node(self, node):
        self.nodes[node.id] = node
        self.graph.add_node(node.id)
        for inp in node.inputs:
            self.graph.add_edge(inp, node.id)

    def load_from_yaml(self, yaml_path: str) -> None:
        """Load DAG definition from a YAML file.

        Parses YAML configuration and populates this DAG instance with nodes
        and their connections. Also stores metadata for visualization.

        Args:
            yaml_path: Path to YAML file containing DAG definition

        Raises:
            FileNotFoundError: If YAML file not found
            ValueError: If YAML structure is invalid

        Example:
            >>> dag = MetricDAG()
            >>> dag.load_from_yaml('tests/dag_cfg/simple_speed_compliance.yaml')
            >>> dag.visualize(output_path='my_dag')
        """
        yaml_file = Path(yaml_path)
        if not yaml_file.exists():
            raise FileNotFoundError(f"DAG YAML file not found: {yaml_path}")

        with open(yaml_file, 'r') as f:
            config = yaml.safe_load(f)

        # Extract metadata and nodes
        self.metadata['description'] = config.get('description', '')
        self.metadata['source_file'] = str(yaml_file.resolve())

        nodes_config = config.get('nodes', {})
        if not nodes_config:
            raise ValueError("No nodes found in DAG YAML configuration")

        # Add nodes to DAG
        for node_id, node_config in sorted(nodes_config.items(), key=lambda x: int(x[0])):
            node_id = int(node_id)
            node_type = node_config.get('type')
            node_name = node_config.get('name')
            node_display_name = node_config.get('node_name')
            inputs = node_config.get('inputs') or []
            params = node_config.get('params') or {}
            node_description = node_config.get('description') or ''
            tags = node_config.get('tags') or []
            analyzer_names = node_config.get('analyzer_names') or []

            # Create DagNode instance
            node = DagNode(
                id=node_id,
                type=node_type,
                instance=None,  # Instance will be created at runtime
                inputs=inputs,
                params=params,
                description=node_description,
                tags=tags,
                analyzer_names=analyzer_names,
                name=node_name,
                node_name=node_display_name,
            )

            self.add_node(node)

    def validate(self):
        if not nx.is_directed_acyclic_graph(self.graph):
            raise ValueError("Metric DAG contains a cycle!")

    def run(self, context):
        self.validate()
        cache = {}
        for node_id in nx.topological_sort(self.graph):
            node = self.nodes[node_id]
            inputs = {i: cache[i] for i in node.inputs}
            cache[node_id] = node.instance.run(inputs=inputs, context=context)
        return cache

    def visualize(
        self,
        output_format: str = 'png',
        output_path: Optional[str] = None,
        view: bool = False,
        title: Optional[str] = None
    ) -> str:
        """Generate a visual representation of this DAG and save to file.

        Args:
            output_format: Output format ('png', 'svg', 'pdf')
            output_path: Path to save output file (without extension)
                        If None, generates filename based on node count
            view: If True, attempt to open the generated image
            title: Optional title for the graph. If None, uses DAG description from metadata

        Returns:
            Path to the generated visualization file

        Example:
            >>> dag = MetricDAG()
            >>> dag.load_from_yaml('tests/dag_cfg/simple_speed_compliance.yaml')
            >>> dag.visualize()
            >>> dag.visualize(output_format='svg', view=True)
        """
        from humex.metrics.dag.dag_visualizer import visualize_dag

        # Use stored metadata description as title if not provided
        if title is None:
            title = self.metadata.get('description', None)

        return visualize_dag(
            self,
            output_format=output_format,
            output_path=output_path,
            view=view,
            title=title
        )

