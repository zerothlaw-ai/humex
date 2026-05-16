"""DAG construction helper for programmatic DAG building."""

from typing import Dict, List, Optional, Any
from .common import (
    DAGNodeDef,
    ConverterError,
    get_next_node_id,
    detect_cycle,
    COMPARATOR_OPS,
    REDUCER_OPS,
    validate_comparator,
    validate_reducer
)


class DAGBuilder:
    """Helper class for programmatically building DAG structures.

    Provides methods to add nodes and manage connections without
    directly manipulating node IDs.
    """

    def __init__(self):
        """Initialize empty DAG builder."""
        self.nodes: Dict[int, DAGNodeDef] = {}

    @property
    def next_id(self) -> int:
        """Get the next available node ID."""
        return get_next_node_id(self.nodes)

    def add_monitor_node(self, monitor_name: str, description: str = "") -> int:
        """Add a monitor node to the DAG.

        Args:
            monitor_name: Name of the monitor
            description: Optional description

        Returns:
            Node ID of the created node
        """
        node_id = self.next_id
        self.nodes[node_id] = DAGNodeDef(
            id=node_id,
            type="monitor",
            name=monitor_name,
            inputs=[],
            params={},
            description=description,
            tags=["data_source"]
        )
        return node_id

    def add_operator_node(
        self,
        op_name: str,
        op_type: str,
        inputs: List[int],
        params: Optional[Dict[str, Any]] = None,
        description: str = "",
        analyzer_names: Optional[List[str]] = None
    ) -> int:
        """Add an operator node to the DAG.

        Args:
            op_name: Name/identifier for this operator instance
            op_type: Type of operator (reduce, compare, mask, transform, etc.)
            inputs: List of input node IDs
            params: Operation parameters
            description: Optional description
            analyzer_names: Optional list of analyzer names this node belongs to

        Returns:
            Node ID of the created node
        """
        if not inputs:
            raise ConverterError(f"Operator {op_type} must have at least one input")

        if params is None:
            params = {}

        if analyzer_names is None:
            analyzer_names = []

        node_id = self.next_id
        self.nodes[node_id] = DAGNodeDef(
            id=node_id,
            type="operator",
            name=op_type,
            inputs=inputs,
            params=params,
            description=description,
            tags=[],
            analyzer_names=analyzer_names
        )
        return node_id

    def add_reduce_node(
        self,
        input_id: int,
        op: str,
        description: str = ""
    ) -> int:
        """Add a reduce operator node.

        Args:
            input_id: Input node ID
            op: Reduction operation (min, max, any, all, not_any)
            description: Optional description

        Returns:
            Node ID of the reduce operator
        """
        if not validate_reducer(op):
            raise ConverterError(f"Unknown reducer operation: {op}")

        return self.add_operator_node(
            op_name="reduce",
            op_type="reduce",
            inputs=[input_id],
            params={"op": op},
            description=description
        )

    def add_compare_node(
        self,
        input_id: int,
        op_symbol: str,
        threshold: Any,
        description: str = "",
        analyzer_names: Optional[List[str]] = None
    ) -> int:
        """Add a compare operator node.

        Args:
            input_id: Input node ID
            op_symbol: Comparison operator (<, <=, >, >=, ==, !=)
            threshold: Threshold value to compare against
            description: Optional description
            analyzer_names: Optional list of analyzer names this node belongs to

        Returns:
            Node ID of the compare operator
        """
        if not validate_comparator(op_symbol):
            raise ConverterError(f"Unknown comparator: {op_symbol}")

        return self.add_operator_node(
            op_name="compare",
            op_type="compare",
            inputs=[input_id],
            params={
                "op_symbol": op_symbol,
                "threshold": threshold
            },
            description=description,
            analyzer_names=analyzer_names
        )

    def add_mask_node(
        self,
        condition_input: int,
        value_input: int,
        description: str = ""
    ) -> int:
        """Add a mask operator node for conditional evaluation.

        Args:
            condition_input: Input node for condition (boolean values)
            value_input: Input node for values to mask
            description: Optional description

        Returns:
            Node ID of the mask operator
        """
        return self.add_operator_node(
            op_name="mask",
            op_type="mask",
            inputs=[condition_input, value_input],
            params={"mode": "while"},
            description=description
        )

    def add_transform_node(
        self,
        input_id: int,
        transform_type: str,
        params: Optional[Dict[str, Any]] = None,
        description: str = ""
    ) -> int:
        """Add a transform operator node.

        Args:
            input_id: Input node ID
            transform_type: Type of transformation (e.g., 'abs')
            params: Optional transformation parameters
            description: Optional description

        Returns:
            Node ID of the transform operator
        """
        return self.add_operator_node(
            op_name="transform",
            op_type="transform",
            inputs=[input_id],
            params=params or {"sign": transform_type},
            description=description
        )

    def add_observe_node(
        self,
        input_id: int,
        description: str = "",
        analyzer_names: Optional[List[str]] = None
    ) -> int:
        """Add an observe operator node (no-op terminal for data inspection).

        Args:
            input_id: Input node ID
            description: Optional description
            analyzer_names: Optional list of analyzer names this node belongs to

        Returns:
            Node ID of the observe operator
        """
        return self.add_operator_node(
            op_name="observe",
            op_type="observe",
            inputs=[input_id],
            params={},
            description=description,
            analyzer_names=analyzer_names
        )

    def add_aggregate_node(
        self,
        input_ids: List[int],
        op: str = "all",
        description: str = ""
    ) -> int:
        """Add an aggregate operator node to combine multiple inputs.

        Args:
            input_ids: List of input node IDs
            op: Aggregation operation (all, any)
            description: Optional description

        Returns:
            Node ID of the aggregate operator
        """
        if len(input_ids) < 2:
            raise ConverterError("Aggregate node requires at least 2 inputs")

        return self.add_operator_node(
            op_name="aggregate",
            op_type="aggregate",
            inputs=input_ids,
            params={"op": op},
            description=description
        )

    def get_node(self, node_id: int) -> Optional[DAGNodeDef]:
        """Get a node by ID.

        Args:
            node_id: Node ID

        Returns:
            Node definition or None if not found
        """
        return self.nodes.get(node_id)

    def connect(self, from_id: int, to_id: int) -> None:
        """Connect one node to another (add edge).

        Args:
            from_id: Source node ID
            to_id: Target node ID
        """
        if from_id not in self.nodes:
            raise ConverterError(f"Source node {from_id} not found")
        if to_id not in self.nodes:
            raise ConverterError(f"Target node {to_id} not found")

        target_node = self.nodes[to_id]
        if from_id not in target_node.inputs:
            target_node.inputs.append(from_id)

    def validate(self) -> bool:
        """Validate DAG structure.

        Checks:
        - No cycles
        - All input references are valid
        - All operators have inputs

        Returns:
            True if valid

        Raises:
            ConverterError if invalid
        """
        if detect_cycle(self.nodes):
            raise ConverterError("Cycle detected in DAG")

        for node_id, node in self.nodes.items():
            # Operators must have inputs
            if node.type == "operator" and not node.inputs:
                raise ConverterError(f"Operator node {node_id} has no inputs")

            # All input references must exist
            for input_id in node.inputs:
                if input_id not in self.nodes:
                    raise ConverterError(
                        f"Node {node_id} references missing input node {input_id}"
                    )

        return True

    def build(self, description: str = "") -> Dict:
        """Build final DAG structure for YAML serialization.

        Args:
            description: DAG description

        Returns:
            Dictionary suitable for YAML output
        """
        self.validate()

        return {
            'description': description,
            'nodes': {
                str(node_id): {
                    'type': node.type,
                    'name': node.name,
                    'inputs': node.inputs,
                    'params': node.params,
                    'description': node.description,
                    'tags': node.tags,
                    'analyzer_names': node.analyzer_names,
                }
                for node_id, node in sorted(self.nodes.items())
            }
        }

    def copy(self) -> 'DAGBuilder':
        """Create a copy of this builder with same nodes.

        Returns:
            New DAGBuilder with copied nodes
        """
        new_builder = DAGBuilder()
        for node_id, node in self.nodes.items():
            new_builder.nodes[node_id] = DAGNodeDef(
                id=node.id,
                type=node.type,
                name=node.name,
                inputs=list(node.inputs),
                params=node.params.copy(),
                description=node.description,
                tags=list(node.tags)
            )
        return new_builder

    def clear(self) -> None:
        """Clear all nodes."""
        self.nodes.clear()
