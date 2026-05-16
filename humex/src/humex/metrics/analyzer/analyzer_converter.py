"""Convert analyzer.yaml files to DAG nodes.

This module handles conversion of analyzer configuration files (list of metric items)
into DAG node chains, where each metric becomes a pipeline:
- Base node (monitor or logic reference)
- Optional transform node (for sign transformations like abs)
- Optional aggregator node (for operations like continuous_duration)
- Reducer node (min/max/any/all/not_any)
- Compare node (with comparator and threshold)
"""

import yaml
from pathlib import Path
from typing import Dict, Optional, List, Set
from .common import (
    ConverterError,
    AnalyzerNotFoundError,
    CircularDependencyError,
    DAGNodeDef,
    validate_comparator,
    validate_reducer,
    validate_sign
)
from .dag_builder import DAGBuilder
from .logic_converter import LogicConverter


class AnalyzerConverter:
    """Converts analyzer.yaml files to DAG nodes.

    Handles:
    - Loading and parsing analyzer YAML files
    - Converting metric items to DAG node chains
    - Handling nested logic references
    - Detecting circular dependencies
    - Building intermediate DAG representation
    """

    def __init__(self, analyzer_dir: Optional[str] = None, logic_dir: Optional[str] = None):
        """Initialize analyzer converter.

        Args:
            analyzer_dir: Directory containing analyzer YAML files.
                         If None, uses default analyzer path.
            logic_dir: Directory containing logic YAML files for LogicConverter.
                      If None, uses default logic path.
        """
        if analyzer_dir is None:
            try:
                from humex.utils.paths import ANALYZER_PATH
                self.analyzer_dir = ANALYZER_PATH
            except (ImportError, AttributeError):
                self.analyzer_dir = str(Path(__file__).parent.parent.parent.parent / "libs" / "analyzers")
        else:
            self.analyzer_dir = analyzer_dir

        self.builder = DAGBuilder()
        self.logic_converter = LogicConverter(logic_dir)
        self.analyzer_cache: Dict[str, int] = {}  # Maps metric_name -> leaf_node_id
        self.conversion_stack: Set[str] = set()  # Track conversion stack for cycle detection

    def convert(self, analyzer_name: str) -> int:
        """Convert an analyzer.yaml file to a DAG with metric nodes.

        Args:
            analyzer_name: Name of the analyzer file (without .yaml extension)

        Returns:
            Node ID of the last metric's leaf node (all metrics are in the DAG)

        Raises:
            AnalyzerNotFoundError: If analyzer file cannot be found
            CircularDependencyError: If circular dependencies detected
            ConverterError: If conversion fails
        """
        # Load analyzer YAML
        analyzer_config = self._load_analyzer(analyzer_name)

        # Convert each metric item in the analyzer
        last_metric_id = None
        for metric_item in analyzer_config:
            metric_name = metric_item.get('name')
            if not metric_name:
                raise ConverterError("Metric item must have 'name' field")

            try:
                metric_node_id = self._convert_metric(metric_item)
                last_metric_id = metric_node_id
            except ConverterError as e:
                raise ConverterError(f"Failed to convert metric '{metric_name}': {e}")

        if last_metric_id is None:
            raise ConverterError(f"Analyzer '{analyzer_name}' has no metrics")

        return last_metric_id

    def _convert_metric(self, metric_item: Dict) -> int:
        """Convert a single metric item to a DAG node chain.

        Pipeline:
        1. Base node (monitor or logic reference)
        2. Optional transform node (for sign transformation)
        3. Optional aggregator node
        4. Reducer node
        5. Compare node

        Args:
            metric_item: Dictionary with metric configuration

        Returns:
            Node ID of the leaf node (compare operator)

        Raises:
            ConverterError: If metric format is invalid
        """
        metric_name = metric_item.get('name', 'unnamed')

        # Step 1: Get base node from monitor or logic
        if 'monitor' in metric_item:
            monitor_name = metric_item['monitor']
            base_node_id = self.builder.add_monitor_node(
                monitor_name=monitor_name,
                description=f"Monitor '{monitor_name}' for metric '{metric_name}'"
            )
        elif 'logic' in metric_item:
            logic_name = metric_item['logic']
            # Use LogicConverter to get the logic DAG nodes
            base_node_id = self.logic_converter.convert(logic_name)
            # Merge logic converter's nodes into our builder
            self._merge_from_logic_converter()
        else:
            raise ConverterError(
                f"Metric '{metric_name}' must have either 'monitor' or 'logic' key"
            )

        current_node_id = base_node_id

        # Step 2: Optional transform node (for sign transformation like abs)
        if 'sign' in metric_item:
            sign = metric_item['sign']
            if not validate_sign(sign):
                raise ConverterError(f"Invalid sign transformation: {sign}")

            current_node_id = self.builder.add_transform_node(
                input_id=current_node_id,
                transform_type=sign,
                params={"sign": sign},
                description=f"Transform: {sign} for metric '{metric_name}'"
            )

        # Step 3: Optional aggregator node
        if 'aggregator' in metric_item:
            aggregator = metric_item['aggregator']
            current_node_id = self.builder.add_operator_node(
                op_name="aggregator",
                op_type="aggregator",
                inputs=[current_node_id],
                params={"aggregator": aggregator},
                description=f"Aggregator: {aggregator} for metric '{metric_name}'"
            )

        # Step 3.5: Observer node (terminates early, no reducer/comparator needed)
        if metric_item.get('observer', False):
            current_node_id = self.builder.add_observe_node(
                input_id=current_node_id,
                description=f"Observe: metric '{metric_name}' (no verdict)",
                analyzer_names=[metric_name]
            )
            self.analyzer_cache[metric_name] = current_node_id
            return current_node_id

        # Step 4: Reducer node (required)
        if 'reducer' not in metric_item:
            raise ConverterError(f"Metric '{metric_name}' missing required 'reducer' field")

        reducer = metric_item['reducer']
        if not validate_reducer(reducer):
            raise ConverterError(f"Invalid reducer for metric '{metric_name}': {reducer}")

        current_node_id = self.builder.add_reduce_node(
            input_id=current_node_id,
            op=reducer,
            description=f"Reduce: {reducer} for metric '{metric_name}'"
        )

        # Step 5: Compare node (required)
        if 'comparator' not in metric_item:
            raise ConverterError(f"Metric '{metric_name}' missing required 'comparator' field")
        if 'threshold' not in metric_item:
            raise ConverterError(f"Metric '{metric_name}' missing required 'threshold' field")

        comparator = metric_item['comparator']
        threshold = metric_item['threshold']

        if not validate_comparator(comparator):
            raise ConverterError(f"Invalid comparator for metric '{metric_name}': {comparator}")

        current_node_id = self.builder.add_compare_node(
            input_id=current_node_id,
            op_symbol=comparator,
            threshold=threshold,
            description=f"Compare: {comparator} {threshold} for metric '{metric_name}'",
            analyzer_names=[metric_name]  # Leaf node: belongs to this metric
        )

        # Cache the metric result
        self.analyzer_cache[metric_name] = current_node_id

        return current_node_id

    def _merge_from_logic_converter(self):
        """Merge nodes from logic converter's builder into this builder.

        This is needed when metrics reference logic files.
        """
        logic_builder = self.logic_converter.get_builder()
        # Merge the nodes, remapping IDs to avoid conflicts
        for node_id, node in logic_builder.nodes.items():
            new_id = self.builder.next_id
            remapped_inputs = []
            for inp in node.inputs:
                # Check if this input was already remapped
                remapped_inputs.append(inp)

            self.builder.nodes[new_id] = DAGNodeDef(
                id=new_id,
                type=node.type,
                name=node.name,
                inputs=remapped_inputs,
                params=node.params.copy(),
                description=node.description,
                tags=list(node.tags)
            )

    def _load_analyzer(self, analyzer_name: str) -> List[Dict]:
        """Load analyzer YAML file.

        Args:
            analyzer_name: Name of the analyzer file (without .yaml extension)

        Returns:
            List of metric item dictionaries

        Raises:
            AnalyzerNotFoundError: If analyzer file cannot be found
        """
        analyzer_path = Path(self.analyzer_dir) / f"{analyzer_name}.yaml"

        if not analyzer_path.exists():
            raise AnalyzerNotFoundError(
                f"Analyzer file not found: {analyzer_path}"
            )

        try:
            with open(analyzer_path, 'r') as f:
                config = yaml.safe_load(f)

            if not isinstance(config, list):
                raise ConverterError(
                    f"Analyzer YAML must be a list, got {type(config).__name__}"
                )

            return config

        except yaml.YAMLError as e:
            raise ConverterError(f"Failed to parse analyzer YAML: {e}")
        except IOError as e:
            raise ConverterError(f"Failed to read analyzer file: {e}")

    def build(self, description: str = "") -> Dict:
        """Build final DAG structure from converted analyzer.

        Args:
            description: Optional DAG description

        Returns:
            Dictionary suitable for YAML serialization

        Raises:
            ConverterError: If DAG structure is invalid
        """
        return self.builder.build(description)

    def get_builder(self) -> DAGBuilder:
        """Get the underlying DAG builder.

        Returns:
            DAGBuilder instance with all converted nodes
        """
        return self.builder

    def get_logic_converter(self) -> LogicConverter:
        """Get the underlying LogicConverter.

        Returns:
            LogicConverter instance
        """
        return self.logic_converter

    def clear(self) -> None:
        """Clear all converted analyzers and builder state."""
        self.builder.clear()
        self.logic_converter.clear()
        self.analyzer_cache.clear()
        self.conversion_stack.clear()
