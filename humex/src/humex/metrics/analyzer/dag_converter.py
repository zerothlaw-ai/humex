"""Unified DAG converter for orchestrating logic and analyzer conversions."""

import yaml
from typing import Dict, Optional, List
from pathlib import Path
from .common import ConverterError
from .dag_builder import DAGBuilder
from .logic_converter import LogicConverter
from .analyzer_converter import AnalyzerConverter


class DAGConverter:
    """Unified converter for transforming logic and analyzer configs to DAG.

    Orchestrates conversion of both logic.yaml and analyzer.yaml files,
    managing shared DAG builder state and coordinating references.
    """

    def __init__(self, logic_dir: Optional[str] = None, analyzer_dir: Optional[str] = None):
        """Initialize unified DAG converter.

        Args:
            logic_dir: Directory containing logic YAML files.
            analyzer_dir: Directory containing analyzer YAML files.
        """
        self.logic_converter = LogicConverter(logic_dir)
        self.analyzer_converter = AnalyzerConverter(analyzer_dir, logic_dir)
        self.builder = DAGBuilder()

    def convert_logic(self, logic_name: str) -> int:
        """Convert a logic file to DAG nodes.

        Args:
            logic_name: Name of the logic file (without .yaml extension)

        Returns:
            Node ID of the logic's leaf node
        """
        node_id = self.logic_converter.convert(logic_name)
        self._merge_builders()
        return node_id

    def convert_analyzer(self, analyzer_name: str) -> int:
        """Convert an analyzer file to DAG nodes.

        Args:
            analyzer_name: Name of the analyzer file (without .yaml extension)

        Returns:
            Node ID of the last metric's leaf node
        """
        node_id = self.analyzer_converter.convert(analyzer_name)
        self._merge_builders()
        return node_id

    def convert_logic_and_analyzer(
        self,
        logic_name: Optional[str] = None,
        analyzer_name: Optional[str] = None
    ) -> Dict[str, int]:
        """Convert both logic and analyzer files.

        Args:
            logic_name: Name of logic file (optional)
            analyzer_name: Name of analyzer file (optional)

        Returns:
            Dict with 'logic' and/or 'analyzer' keys containing leaf node IDs
        """
        result = {}

        if logic_name:
            result['logic'] = self.convert_logic(logic_name)

        if analyzer_name:
            result['analyzer'] = self.convert_analyzer(analyzer_name)

        return result

    def _merge_builders(self):
        """Merge logic and analyzer converter builders into main builder."""
        # Merge logic converter nodes
        for node_id, node in self.logic_converter.builder.nodes.items():
            if node_id not in self.builder.nodes:
                self.builder.nodes[node_id] = node

        # Merge analyzer converter nodes
        for node_id, node in self.analyzer_converter.builder.nodes.items():
            if node_id not in self.builder.nodes:
                self.builder.nodes[node_id] = node

    def build(self, description: str = "") -> Dict:
        """Build final DAG structure.

        Args:
            description: Optional DAG description

        Returns:
            Dictionary suitable for YAML serialization
        """
        self._merge_builders()
        return self.builder.build(description)

    def save_to_yaml(self, output_path: str, description: str = "") -> None:
        """Save DAG structure to YAML file.

        Args:
            output_path: Path to output YAML file
            description: Optional DAG description
        """
        dag_dict = self.build(description)

        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            yaml.dump(dag_dict, f, default_flow_style=False, sort_keys=False)

    def get_builder(self) -> DAGBuilder:
        """Get the main DAG builder.

        Returns:
            DAGBuilder instance
        """
        self._merge_builders()
        return self.builder

    def get_logic_converter(self) -> LogicConverter:
        """Get the LogicConverter.

        Returns:
            LogicConverter instance
        """
        return self.logic_converter

    def get_analyzer_converter(self) -> AnalyzerConverter:
        """Get the AnalyzerConverter.

        Returns:
            AnalyzerConverter instance
        """
        return self.analyzer_converter

    def clear(self) -> None:
        """Clear all converted data."""
        self.builder.clear()
        self.logic_converter.clear()
        self.analyzer_converter.clear()
