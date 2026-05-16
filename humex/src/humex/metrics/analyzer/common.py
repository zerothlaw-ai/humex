"""Shared types and utilities for analyzer/logic to DAG conversion."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# Custom Exceptions
class ConverterError(Exception):
    """Base exception for converter errors."""
    pass


class LogicNotFoundError(ConverterError):
    """Raised when a logic file cannot be found."""
    pass


class AnalyzerNotFoundError(ConverterError):
    """Raised when an analyzer file cannot be found."""
    pass


class CircularDependencyError(ConverterError):
    """Raised when circular logic dependencies are detected."""
    pass


# Data Classes
@dataclass
class DAGNodeDef:
    """Intermediate representation of a DAG node for building.

    Attributes:
        id: Unique node identifier
        type: Node type - "monitor" or "operator"
        name: Monitor name or operator name
        inputs: List of input node IDs
        params: Operation parameters
        description: Optional node description
        tags: Optional list of tags
        analyzer_names: List of analyzer names this node belongs to (empty for shared nodes)
    """
    id: int
    type: str  # "monitor" or "operator"
    name: str
    inputs: List[int] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    analyzer_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary format for YAML serialization."""
        return {
            'type': self.type,
            'name': self.name,
            'inputs': self.inputs,
            'params': self.params,
            'description': self.description,
            'tags': self.tags,
            'analyzer_names': self.analyzer_names,
        }


# Operator Mapping Constants
REDUCER_OPS = {
    'min': 'min',
    'max': 'max',
    'any': 'any',
    'all': 'all',
    'not_any': 'not_any'
}

COMPARATOR_OPS = {
    '<': '<',
    '<=': '<=',
    '>': '>',
    '>=': '>=',
    '==': '==',
    '!=': '!='
}

SIGN_OPS = {
    'abs': 'abs'
}


# Utility Functions
def validate_comparator(comp: str) -> bool:
    """Check if comparator is valid."""
    return comp in COMPARATOR_OPS


def validate_reducer(reducer: str) -> bool:
    """Check if reducer operation is valid."""
    return reducer in REDUCER_OPS


def validate_sign(sign: Optional[str]) -> bool:
    """Check if sign transformation is valid."""
    if sign is None:
        return True
    return sign in SIGN_OPS


def get_next_node_id(nodes: Dict[int, DAGNodeDef]) -> int:
    """Get the next available node ID."""
    if not nodes:
        return 1
    return max(nodes.keys()) + 1


def merge_node_dicts(*node_dicts: Dict[int, DAGNodeDef]) -> Dict[int, DAGNodeDef]:
    """Merge multiple node dictionaries with ID remapping.

    When merging, adjust node IDs in the second and subsequent dicts
    to avoid conflicts.

    Args:
        *node_dicts: Variable number of node dictionaries to merge

    Returns:
        Merged dictionary with adjusted IDs
    """
    if not node_dicts:
        return {}

    result = dict(node_dicts[0])

    for node_dict in node_dicts[1:]:
        if not node_dict:
            continue

        offset = get_next_node_id(result)
        id_mapping = {old_id: old_id + offset for old_id in node_dict.keys()}

        for old_id, node in node_dict.items():
            new_id = id_mapping[old_id]
            # Remap input node IDs
            remapped_inputs = [id_mapping.get(inp, inp) for inp in node.inputs]

            result[new_id] = DAGNodeDef(
                id=new_id,
                type=node.type,
                name=node.name,
                inputs=remapped_inputs,
                params=node.params.copy(),
                description=node.description,
                tags=list(node.tags),
                analyzer_names=list(node.analyzer_names)
            )

    return result


def detect_cycle(nodes: Dict[int, DAGNodeDef]) -> bool:
    """Detect if DAG has cycles using DFS.

    Args:
        nodes: Dictionary of node definitions

    Returns:
        True if cycle exists, False otherwise
    """
    # Build adjacency list
    graph = {node_id: node.inputs for node_id, node in nodes.items()}

    # Track visited states: 0=unvisited, 1=visiting, 2=visited
    state = {node_id: 0 for node_id in graph}

    def has_cycle_dfs(node_id: int) -> bool:
        if state[node_id] == 1:  # Currently visiting
            return True
        if state[node_id] == 2:  # Already visited
            return False

        state[node_id] = 1
        for input_id in graph.get(node_id, []):
            if has_cycle_dfs(input_id):
                return True
        state[node_id] = 2
        return False

    for node_id in graph:
        if state[node_id] == 0:
            if has_cycle_dfs(node_id):
                return True

    return False


def build_dag_structure(nodes: Dict[int, DAGNodeDef], description: str = "") -> Dict:
    """Convert nodes to DAG YAML structure.

    Args:
        nodes: Dictionary of node definitions
        description: DAG description

    Returns:
        Dictionary suitable for YAML serialization
    """
    if detect_cycle(nodes):
        raise ConverterError("Cycle detected in DAG structure")

    return {
        'description': description,
        'nodes': {
            str(node_id): node.to_dict()
            for node_id, node in sorted(nodes.items())
        }
    }