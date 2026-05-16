"""Monitor discovery API for listing available monitors and their metadata.

This module provides an API for frontend applications to discover available monitors,
their parameters, descriptions, and usage information. Enables dynamic UI generation
for DAG assembly tools.
"""

import inspect
from typing import Dict, Any, List

from humex.metrics.monitors import monitor_mapping


class MonitorDiscoveryAPI:
    """API for discovering available monitors and their metadata.

    Provides comprehensive information about all registered monitors including
    descriptions, parameters, and signatures. Useful for frontend applications
    that need to display available monitors to users for DAG assembly.
    """

    @staticmethod
    def _extract_description(cls) -> str:
        """Extract description from class docstring.

        Args:
            cls: Monitor class

        Returns:
            First line of docstring or empty string
        """
        doc = inspect.getdoc(cls)
        if doc:
            # Return first line (before double newline or first period)
            first_line = doc.split('\n')[0].strip()
            return first_line
        return ""

    @staticmethod
    def _extract_parameters(cls) -> List[Dict[str, Any]]:
        """Extract parameter information from monitor class.

        Checks for a PARAMS class attribute first (used by monitors that accept
        DAG-configurable params via self.params). Falls back to inspecting the
        calculate() method signature for backward compatibility.

        PARAMS format (list of dicts):
            [{"name": "buffer_lon", "type": "float", "default": 0.0, "description": "..."}, ...]

        Args:
            cls: Monitor class

        Returns:
            List of parameter dictionaries with name, type, required, and description
        """
        # Prefer explicit PARAMS class attribute (for monitors using self.params)
        if hasattr(cls, 'PARAMS') and cls.PARAMS:
            parameters = []
            for p in cls.PARAMS:
                param_info = {
                    "name": p["name"],
                    "type": p.get("type", "Any"),
                    "required": p.get("required", False),
                    "description": p.get("description", f"Parameter: {p['name']}"),
                }
                if "default" in p:
                    param_info["default"] = p["default"]
                if "allowed_values" in p:
                    param_info["allowed_values"] = p["allowed_values"]
                if "multi_select" in p:
                    param_info["multi_select"] = p["multi_select"]
                parameters.append(param_info)
            return parameters

        # Fallback: introspect calculate() method signature
        parameters = []

        try:
            sig = inspect.signature(cls.calculate)

            for param_name, param in sig.parameters.items():
                # Skip 'self'
                if param_name == 'self':
                    continue

                # Use __name__ for clean type strings (e.g. "float" not "<class 'float'>")
                if param.annotation != inspect.Parameter.empty and hasattr(param.annotation, '__name__'):
                    type_str = param.annotation.__name__
                elif param.annotation != inspect.Parameter.empty:
                    type_str = str(param.annotation)
                else:
                    type_str = "Any"

                param_info = {
                    "name": param_name,
                    "type": type_str,
                    "required": param.default == inspect.Parameter.empty,
                    "description": f"Parameter: {param_name}"
                }

                # Add default value if it exists
                if param.default != inspect.Parameter.empty:
                    param_info["default"] = param.default

                parameters.append(param_info)

        except Exception:
            pass  # Return empty list if unable to extract

        return parameters

    def get_monitors_info(self) -> Dict[str, Any]:
        """Get comprehensive metadata for all available monitors.

        Returns information about each monitor including name, description,
        parameters, and return type. Useful for building UI components that
        allow users to select monitors for DAG construction.

        Returns:
            Dictionary with keys:
            - 'total_count': int - Total number of monitors
            - 'monitors': List[Dict] - List of monitor metadata dictionaries

            Each monitor dictionary contains:
            - 'name': str - Snake-case monitor name (registry key)
            - 'class_name': str - CamelCase class name
            - 'description': str - Human-readable description
            - 'parameters': List[Dict] - Parameter information
            - 'return_type': str - Output type (always 'MetricTrace')

        Example:
            >>> api = MonitorDiscoveryAPI()
            >>> info = api.get_monitors_info()
            >>> print(info['total_count'])
            20
            >>> print(info['monitors'][0]['name'])
            'ego_collision'
        """
        monitors_list = []

        # Iterate through monitor_mapping to get all unique monitors
        # (there may be duplicates with snake_case and CamelCase keys)
        processed_classes = set()

        for monitor_name, monitor_class in monitor_mapping.items():
            # Skip if we've already processed this class
            class_id = id(monitor_class)
            if class_id in processed_classes:
                continue
            processed_classes.add(class_id)

            # Get class name
            class_name = monitor_class.__name__

            # For consistency, use snake_case name if available
            # Otherwise derive from class name
            snake_case_name = None
            for key, cls in monitor_mapping.items():
                if cls is monitor_class and '_' in key:
                    snake_case_name = key
                    break

            if not snake_case_name:
                # Convert CamelCase to snake_case
                snake_case_name = ''.join(
                    ['_' + c.lower() if c.isupper() else c for c in class_name]
                ).lstrip('_')

            monitor_info = {
                "name": snake_case_name,
                "class_name": class_name,
                "description": self._extract_description(monitor_class),
                "parameters": self._extract_parameters(monitor_class),
                "return_type": "MetricTrace",
                "output_type": monitor_class.OUTPUT_TYPE.value
            }

            monitors_list.append(monitor_info)

        # Sort by name for consistent ordering
        monitors_list.sort(key=lambda x: x['name'])

        return {
            "total_count": len(monitors_list),
            "monitors": monitors_list
        }

    def get_monitor_info(self, monitor_name: str) -> Dict[str, Any]:
        """Get metadata for a specific monitor by name.

        Args:
            monitor_name: Name of the monitor (snake_case or CamelCase)

        Returns:
            Dictionary with monitor metadata

        Raises:
            ValueError: If monitor not found
        """
        if monitor_name not in monitor_mapping:
            raise ValueError(f"Monitor '{monitor_name}' not found in registry")

        monitor_class = monitor_mapping[monitor_name]

        return {
            "name": monitor_name,
            "class_name": monitor_class.__name__,
            "description": self._extract_description(monitor_class),
            "parameters": self._extract_parameters(monitor_class),
            "return_type": "MetricTrace",
            "output_type": monitor_class.OUTPUT_TYPE.value
        }
