from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional

@dataclass
class DagNode:
    """Represents a node in a Metric DAG.

    A DAG node can be either a monitor (data source) or an operator (computation).
    Each node has a unique ID, type, optional instance, and can have inputs and parameters.

    Attributes:
        id: Unique integer identifier for the node
        type: "monitor" or "operator"
        instance: a MonitorBase or OperatorBase instance
        inputs: List of input node IDs
        params: Operation parameters
        description: Optional node description
        tags: Optional list of tags for categorization
        analyzer_names: List of analyzer names this node belongs to.
                       For leaf nodes (compare operators): contains exactly one analyzer name (the metric name)
                       For intermediate/monitor nodes: empty list (shared resources)
        name: Node name (operator/monitor type, used for class lookup)
        node_name: User-editable display name (for differentiating same-type nodes)
    """
    id: int                          # Unique integer identifier for the node
    type: str                        # "monitor" or "operator"
    instance: Any                    # a MonitorBase or OperatorBase
    inputs: List[int] = field(default_factory=list)  # IDs of input nodes
    params: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None
    tags: Optional[List[str]] = field(default_factory=list)
    analyzer_names: List[str] = field(default_factory=list)  # Which analyzer(s) this node belongs to
    name: Optional[str] = None       # Operator/monitor type name (for class lookup)
    node_name: Optional[str] = None  # User-editable display name
