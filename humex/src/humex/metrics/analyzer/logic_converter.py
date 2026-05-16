"""Convert logic.yaml files to DAG nodes.

This module handles conversion of logic configuration files (with condition/evaluation
mechanism) into DAG nodes, where:
- Evaluation clauses (metrics to measure) become the value input
- Condition clauses (when to measure) become the condition input
- Together they form a mask operator in the DAG
"""

import yaml
from pathlib import Path
from typing import Dict, Optional, List, Set
from .common import (
    ConverterError,
    LogicNotFoundError,
    CircularDependencyError,
    DAGNodeDef,
    validate_comparator,
    validate_reducer
)
from .dag_builder import DAGBuilder


class LogicConverter:
    """Converts logic.yaml files to DAG nodes.

    Handles:
    - Loading and parsing logic YAML files
    - Converting condition/evaluation mechanism to mask operator
    - Handling nested logic references
    - Detecting circular dependencies
    - Building intermediate DAG representation
    """

    def __init__(self, logic_dir: Optional[str] = None):
        """Initialize logic converter.

        Args:
            logic_dir: Directory containing logic YAML files.
                      If None, uses default logic path from config.
        """
        if logic_dir is None:
            # Try to use default logic path from utils
            try:
                from humex.utils.paths import LOGIC_PATH
                self.logic_dir = LOGIC_PATH
            except (ImportError, AttributeError):
                # Fallback to relative path
                self.logic_dir = str(Path(__file__).parent.parent.parent.parent / "logics")
        else:
            self.logic_dir = logic_dir

        self.builder = DAGBuilder()
        self.logic_cache: Dict[str, int] = {}  # Maps logic_name -> leaf_node_id
        self.conversion_stack: Set[str] = set()  # Track conversion stack for cycle detection

    def convert(self, logic_name: str) -> int:
        """Convert a logic.yaml file to a DAG node.

        Args:
            logic_name: Name of the logic file (without .yaml extension)

        Returns:
            Node ID of the leaf node representing the logic

        Raises:
            LogicNotFoundError: If logic file cannot be found
            CircularDependencyError: If circular logic dependencies detected
            ConverterError: If conversion fails
        """
        # Check cache first
        if logic_name in self.logic_cache:
            return self.logic_cache[logic_name]

        # Check for circular dependencies
        if logic_name in self.conversion_stack:
            raise CircularDependencyError(
                f"Circular logic dependency detected: {logic_name}"
            )

        # Load logic YAML
        logic_config = self._load_logic(logic_name)

        # Track this logic in conversion stack
        self.conversion_stack.add(logic_name)

        try:
            # Convert evaluation clauses to get value input node
            evaluation_nodes = self._convert_sublogic(logic_config.get('evaluation', []))
            if len(evaluation_nodes) == 0:
                raise ConverterError(f"Logic '{logic_name}' has no evaluation clauses")

            # Combine evaluation nodes with AND logic
            if len(evaluation_nodes) == 1:
                evaluation_node_id = evaluation_nodes[0]
            else:
                evaluation_node_id = self.builder.add_aggregate_node(
                    evaluation_nodes,
                    op="all",
                    description=f"Evaluation aggregation for logic '{logic_name}'"
                )

            # Convert condition clauses to get condition input node (if present)
            if 'condition' in logic_config and logic_config['condition']:
                condition_nodes = self._convert_sublogic(logic_config['condition'])

                if len(condition_nodes) == 0:
                    # No condition clauses = always true condition
                    condition_node_id = None
                elif len(condition_nodes) == 1:
                    condition_node_id = condition_nodes[0]
                else:
                    # Combine with AND logic
                    condition_node_id = self.builder.add_aggregate_node(
                        condition_nodes,
                        op="all",
                        description=f"Condition aggregation for logic '{logic_name}'"
                    )
            else:
                # No condition specified = always evaluate
                condition_node_id = None

            # Create mask operator combining condition and evaluation
            if condition_node_id is not None:
                mask_node_id = self.builder.add_mask_node(
                    condition_input=condition_node_id,
                    value_input=evaluation_node_id,
                    description=f"Logic '{logic_name}' evaluation with condition"
                )
            else:
                # No condition = just use evaluation result directly
                mask_node_id = evaluation_node_id

            # Cache the result
            self.logic_cache[logic_name] = mask_node_id

            return mask_node_id

        finally:
            # Remove from conversion stack
            self.conversion_stack.discard(logic_name)

    def _convert_sublogic(self, sublogic: List[Dict]) -> List[int]:
        """Convert a list of logic clauses (AND'd together).

        Args:
            sublogic: List of clause dictionaries with 'monitor' or 'logic' key

        Returns:
            List of node IDs for each clause (to be AND'd together)

        Raises:
            ConverterError: If clause format is invalid
        """
        node_ids = []

        for i, clause in enumerate(sublogic):
            if not isinstance(clause, dict):
                raise ConverterError(f"Clause {i} must be a dictionary")

            # Get base node from monitor or nested logic
            if 'monitor' in clause:
                monitor_name = clause['monitor']
                base_node_id = self.builder.add_monitor_node(
                    monitor_name=monitor_name,
                    description=f"Monitor '{monitor_name}' in sublogic"
                )
            elif 'logic' in clause:
                logic_name = clause['logic']
                # Recursively convert nested logic
                base_node_id = self.convert(logic_name)
            else:
                raise ConverterError(
                    f"Clause {i} must contain either 'monitor' or 'logic' key"
                )

            # If clause has comparator/threshold, add compare operator
            if 'comparator' in clause:
                if 'threshold' not in clause:
                    raise ConverterError(
                        f"Clause {i} has 'comparator' but missing 'threshold'"
                    )

                op_symbol = clause['comparator']
                threshold = clause['threshold']

                if not validate_comparator(op_symbol):
                    raise ConverterError(
                        f"Clause {i} has invalid comparator: {op_symbol}"
                    )

                compare_node_id = self.builder.add_compare_node(
                    input_id=base_node_id,
                    op_symbol=op_symbol,
                    threshold=threshold,
                    description=f"Compare with threshold {threshold}"
                )
                node_ids.append(compare_node_id)
            else:
                # No comparison, use base node as-is
                node_ids.append(base_node_id)

        return node_ids

    def _load_logic(self, logic_name: str) -> Dict:
        """Load logic YAML file.

        Args:
            logic_name: Name of the logic file (without .yaml extension)

        Returns:
            Parsed logic configuration dictionary

        Raises:
            LogicNotFoundError: If logic file cannot be found
        """
        logic_path = Path(self.logic_dir) / f"{logic_name}.yaml"

        if not logic_path.exists():
            raise LogicNotFoundError(
                f"Logic file not found: {logic_path}"
            )

        try:
            with open(logic_path, 'r') as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                raise ConverterError(
                    f"Logic YAML must be a dictionary, got {type(config).__name__}"
                )

            return config

        except yaml.YAMLError as e:
            raise ConverterError(f"Failed to parse logic YAML: {e}")
        except IOError as e:
            raise ConverterError(f"Failed to read logic file: {e}")

    def build(self, description: str = "") -> Dict:
        """Build final DAG structure from converted logic.

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

    def clear(self) -> None:
        """Clear all converted logics and builder state."""
        self.builder.clear()
        self.logic_cache.clear()
        self.conversion_stack.clear()
