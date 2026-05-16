"""DAG Visualizer - Enhanced visualization of metric computation DAGs using Graphviz.

This module provides functionality to generate visual representations of MetricDAG instances
as PNG, SVG, or PDF files with semantic coloring, parameter display, and node grouping.

Features:
- Semantic colors: Monitor (green), Reduce (blue), Transform (purple), Compare (pink), etc.
- Parameter display: Shows operator parameters and thresholds on nodes
- Node grouping: Clusters nodes by analyzer/metric for better organization
- Edge styling: Colored edges and labels for improved clarity
- Legend: Automatic legend showing node types and colors
"""

from pathlib import Path
from typing import Optional, Dict, Set, List, Tuple
from humex.metrics.dag.dag import MetricDAG


def _get_operator_type(node) -> str:
    """Determine the operator type from a node instance.

    Args:
        node: Node instance

    Returns:
        String representing operator type ('reduce', 'transform', 'compare', 'aggregate', 'mask', 'temporal', 'unknown')
    """
    if node.type != "operator":
        return "unknown"

    # First try to use instance class name if available
    if node.instance is not None:
        instance_class = type(node.instance).__name__

        operator_type_map = {
            'ReduceOperator': 'reduce',
            'TransformOperator': 'transform',
            'CompareOperator': 'compare',
            'AggregateOperator': 'aggregate',
            'MaskOperator': 'mask',
            'TemporalOperator': 'temporal',
        }

        result = operator_type_map.get(instance_class, None)
        if result:
            return result

    # Fallback: infer from node name
    if hasattr(node, 'name') and node.name:
        name_lower = node.name.lower()
        if name_lower == 'reduce':
            return 'reduce'
        elif name_lower == 'transform':
            return 'transform'
        elif name_lower == 'compare':
            return 'compare'
        elif name_lower == 'aggregate':
            return 'aggregate'
        elif name_lower == 'mask':
            return 'mask'
        elif name_lower == 'temporal':
            return 'temporal'

    # Final fallback: try to infer from params
    if hasattr(node, 'params') and node.params:
        params = node.params
        if 'op_symbol' in params or 'threshold' in params:
            return 'compare'
        elif 'op' in params:
            op_value = str(params['op']).lower()
            if op_value in ['any', 'all', 'max', 'min', 'sum', 'mean']:
                return 'reduce'
            else:
                return 'transform'

    return 'unknown'


def _get_color_for_node(node) -> str:
    """Get the fill color for a node based on its type.

    Args:
        node: Node instance

    Returns:
        Hex color code for the node
    """
    if node.type == "monitor":
        return "#90EE90"  # Light green for data sources

    if node.type == "operator":
        op_type = _get_operator_type(node)
        color_map = {
            'reduce': '#87CEEB',      # Sky blue
            'transform': '#DDA0DD',   # Plum purple
            'compare': '#FFB6C1',     # Light pink
            'aggregate': '#F0E68C',   # Khaki
            'mask': '#98FB98',        # Pale green
            'temporal': '#B0E0E6',    # Powder blue
            'unknown': '#D3D3D3',     # Light gray
        }
        return color_map.get(op_type, '#D3D3D3')

    return "#CCCCCC"  # Light gray for unknown types


def _get_node_label(node) -> str:
    """Generate an enhanced label for a node in the DAG visualization.

    Includes node ID, name, and operator parameters for operators.

    Args:
        node: Node instance

    Returns:
        Formatted label string for Graphviz
    """
    label = f"{node.id}: {getattr(node, 'name', 'unknown')}"

    # For operators, add parameter information
    if node.type == "operator" and hasattr(node, 'params') and node.params:
        params = node.params
        param_strs = []

        # Handle common operator parameters
        if 'op' in params:
            param_strs.append(f"op: {params['op']}")
        if 'op_symbol' in params:
            param_strs.append(f"op: {params['op_symbol']}")
        if 'threshold' in params:
            param_strs.append(f"threshold: {params['threshold']}")
        if 'transform' in params:
            param_strs.append(f"transform: {params['transform']}")

        if param_strs:
            label += "\\n" + "\\n".join(param_strs)

    return label


def dag_to_dot(dag: MetricDAG, title: Optional[str] = None) -> str:
    """Convert a MetricDAG to Graphviz DOT format with enhanced visualization.

    Includes semantic colors by operator type, parameter display, node grouping by metric,
    edge styling, and automatic legend generation.

    Args:
        dag: MetricDAG instance to visualize
        title: Optional title for the graph

    Returns:
        DOT format string for Graphviz
    """
    lines = ["digraph MetricDAG {"]
    lines.append('  rankdir=LR;  # Left to right layout')
    lines.append('  node [shape=box, style=filled, fontname="Arial"];')
    lines.append('  edge [fontname="Arial"];')

    # Add title if provided
    if title:
        safe_title = title.replace('"', '\\"')
        lines.append(f'  label="{safe_title}";')
        lines.append('  labelloc=top;')

    # Build map of analyzer_names to nodes for clustering
    analyzer_to_nodes: Dict[str, List[int]] = {}
    unassigned_nodes: List[int] = []

    for node_id, node in dag.nodes.items():
        if hasattr(node, 'analyzer_names') and node.analyzer_names:
            # Leaf nodes with analyzer names
            for analyzer_name in node.analyzer_names:
                if analyzer_name not in analyzer_to_nodes:
                    analyzer_to_nodes[analyzer_name] = []
                analyzer_to_nodes[analyzer_name].append(node_id)
        else:
            unassigned_nodes.append(node_id)

    # Create subgraphs for each analyzer/metric (clustering)
    cluster_id = 0
    processed_nodes: Set[int] = set()

    for analyzer_name, leaf_nodes in analyzer_to_nodes.items():
        # Trace back from leaf nodes to find all upstream nodes for this metric
        metric_nodes = set(leaf_nodes)
        to_process = list(leaf_nodes)

        while to_process:
            current_id = to_process.pop(0)
            if current_id in metric_nodes:
                continue
            metric_nodes.add(current_id)

            # Add input nodes
            if current_id in dag.nodes:
                current_node = dag.nodes[current_id]
                for input_id in current_node.inputs:
                    if input_id not in metric_nodes:
                        to_process.append(input_id)

        # Create subgraph for this metric cluster
        safe_analyzer_name = analyzer_name.replace('"', '\\"').replace(' ', '_')
        lines.append(f'  subgraph cluster_{cluster_id} {{')
        lines.append(f'    label="{analyzer_name}";')
        lines.append('    style=filled;')
        lines.append('    color=lightgrey;')
        lines.append('    fontcolor=black;')
        lines.append('    margin=8;')

        # Add nodes in this cluster
        for node_id in sorted(metric_nodes):
            if node_id not in processed_nodes:
                node = dag.nodes[node_id]
                label = _get_node_label(node)
                safe_label = label.replace('"', '\\"')
                color = _get_color_for_node(node)
                lines.append(f'    {node_id} [label="{safe_label}", fillcolor="{color}", fontcolor="black"];')
                processed_nodes.add(node_id)

        lines.append('  }')
        cluster_id += 1

    # Add remaining unassigned nodes outside clusters
    for node_id in unassigned_nodes:
        if node_id not in processed_nodes:
            node = dag.nodes[node_id]
            label = _get_node_label(node)
            safe_label = label.replace('"', '\\"')
            color = _get_color_for_node(node)
            lines.append(f'  {node_id} [label="{safe_label}", fillcolor="{color}", fontcolor="black"];')
            processed_nodes.add(node_id)

    # Add edges for data flow with enhanced styling
    for node_id, node in dag.nodes.items():
        for input_id in node.inputs:
            input_node = dag.nodes[input_id]
            # Color edges based on source node type
            if input_node.type == "monitor":
                edge_color = "#90EE90"  # Green for monitor outputs
            else:
                edge_color = "#FFA500"  # Orange for operator outputs

            lines.append(f'  {input_id} -> {node_id} [color="{edge_color}"];')

    # Add legend subgraph
    lines.append('  subgraph cluster_legend {')
    lines.append('    label="Legend";')
    lines.append('    style=filled;')
    lines.append('    color=white;')
    lines.append('    fontcolor=black;')
    lines.append('    margin=8;')

    legend_entries = [
        ('Monitor', '#90EE90', 'Data source (sensor, calculation)'),
        ('Reduce', '#87CEEB', 'Reduction operation (aggregate, max, min)'),
        ('Transform', '#DDA0DD', 'Transformation operation (abs, normalize)'),
        ('Compare', '#FFB6C1', 'Comparison operation (threshold check)'),
        ('Aggregate', '#F0E68C', 'Aggregation operation (combine)'),
        ('Mask', '#98FB98', 'Masking operation (filter, condition)'),
    ]

    for i, (label_text, color, desc) in enumerate(legend_entries):
        lines.append(f'    legend_{i} [label="{label_text}", fillcolor="{color}", fontcolor="black", shape=box, style=filled];')

    lines.append('  }')

    lines.append("}")
    return "\n".join(lines)


def visualize_dag(
    dag: MetricDAG,
    output_format: str = 'png',
    output_path: Optional[str] = None,
    view: bool = False,
    title: Optional[str] = None
) -> str:
    """Generate a visual representation of the DAG and save to file.

    Requires Graphviz system package to be installed. If not available,
    a RuntimeError will be raised.

    Args:
        dag: MetricDAG instance to visualize
        output_format: Output format ('png', 'svg', 'pdf'). Default: 'png'
        output_path: Path to save output file (without extension).
                     If None, generates filename based on node count
        view: If True, attempt to open the generated image
        title: Optional title for the graph

    Returns:
        Path to the generated file

    Raises:
        ImportError: If graphviz Python package is not installed
        ValueError: If output_format is not supported
        RuntimeError: If Graphviz system executable is not installed
    """
    try:
        from graphviz import Source
    except ImportError:
        raise ImportError(
            "graphviz Python package is required for visualization. "
            "Install it with: pip install graphviz"
        )

    # Validate output format
    valid_formats = ['png', 'svg', 'pdf']
    if output_format.lower() not in valid_formats:
        raise ValueError(f"Unsupported format: {output_format}. Must be one of {valid_formats}")

    # Generate DOT format
    dot_content = dag_to_dot(dag, title=title)

    # Determine output path
    if output_path is None:
        output_path = f"dag_{len(dag.nodes)}_nodes"
    else:
        # Remove extension if provided, but preserve directory path
        path_obj = Path(output_path)
        # Reconstruct path with directory but no extension
        output_path = str(path_obj.parent / path_obj.stem)

    # Render with Graphviz
    try:
        source = Source(dot_content, format=output_format.lower())
        output_file = source.render(output_path, cleanup=True)
        print(f"DAG visualization saved to: {output_file}")

        # Optionally open the file
        if view:
            import subprocess
            import platform
            try:
                if platform.system() == 'Darwin':  # macOS
                    subprocess.run(['open', output_file])
                elif platform.system() == 'Windows':
                    subprocess.run(['start', output_file])
                else:  # Linux
                    subprocess.run(['xdg-open', output_file])
            except Exception as e:
                print(f"Could not open file: {e}")

        return output_file

    except Exception as e:
        if "failed to execute" in str(e) or "ExecutableNotFound" in type(e).__name__:
            # Graphviz executable not installed
            raise RuntimeError(
                f"Graphviz system executable not found. Cannot generate {output_format.upper()} visualization.\n"
                f"To install Graphviz system package:\n"
                f"  Ubuntu/Debian: sudo apt-get install graphviz\n"
                f"  macOS: brew install graphviz\n"
                f"  Windows: Download from https://graphviz.org/download/"
            ) from e
        else:
            raise
