"""Operator discovery API for listing available operators and their metadata.

This module provides an API for frontend applications to discover available operators,
their parameters, descriptions, and usage information. Enables dynamic UI generation
for DAG assembly tools.
"""

import inspect
from typing import Dict, Any, List, Optional

from humex.metrics.dag.dag_evaluator import OPERATOR_MAPPING


class OperatorDiscoveryAPI:
    """API for discovering available operators and their metadata.

    Provides comprehensive information about all registered operators including
    descriptions, parameters, signatures, and allowed values. Useful for frontend
    applications that need to display available operators to users for DAG assembly.
    """

    # Scalar output types for operators (used by frontend for type propagation)
    # "passthrough" means the operator preserves its input type
    KNOWN_OUTPUT_TYPES = {
        "arithmetic": "float",
        "compare": "bool",
        "reduce": "float",
        "logic": "bool",
        "transform": "float",
        "aggregate": "float",
        "duration": "float",
        "mask": "passthrough",
        "observe": "passthrough",
        "within": "passthrough",
        "scenario_window": "passthrough",
        "chain_result": "bool",
    }

    # Known enum-like parameters for operators
    KNOWN_ENUMS = {
        "reduce": {
            "op": ["min", "max", "any", "all", "not_any"]
        },
        "compare": {
            "op_symbol": ["<", "<=", ">", ">=", "==", "!="]
        },
        "aggregate": {
            "op_symbol": ["continuous_duration"]
        },
        "transform": {
            "sign": ["abs"]
        },
        "mask": {
            "mode": ["while"]
        },
        "observe": {},
        "within": {
            "starting": ["not_null", "false", "true"],
            "target": [True, False]
        },
        "logic": {
            "op": ["and", "or"]
        },
        "arithmetic": {
            "op": ["add", "subtract", "multiply", "divide"]
        },
        "chain_result": {
            "mode": ["any_pass", "all_pass"]
        }
    }

    @staticmethod
    def _extract_description(cls) -> str:
        """Extract description from class docstring.

        Args:
            cls: Operator class

        Returns:
            First line of docstring or empty string
        """
        doc = inspect.getdoc(cls)
        if doc:
            # Return first line (before double newline)
            first_line = doc.split('\n')[0].strip()
            return first_line
        return ""

    @staticmethod
    def _simplify_type(annotation) -> str:
        """Convert a type annotation to a simple string name.

        Args:
            annotation: Type annotation from inspect

        Returns:
            Simple type name like "float", "bool", "int", "str"
        """
        if annotation == inspect.Parameter.empty:
            return "Any"
        # For built-in types, use __name__ for clean output (e.g. "float" not "<class 'float'>")
        if hasattr(annotation, '__name__'):
            return annotation.__name__
        return str(annotation)

    @staticmethod
    def _extract_run_parameters(cls) -> List[Dict[str, Any]]:
        """Extract parameter information from run() method signature.

        Args:
            cls: Operator class

        Returns:
            List of parameter dictionaries with name, type, required, allowed_values
        """
        parameters = []

        try:
            sig = inspect.signature(cls.run)

            for param_name, param in sig.parameters.items():
                # Skip 'self'
                if param_name == 'self':
                    continue

                param_info = {
                    "name": param_name,
                    "type": OperatorDiscoveryAPI._simplify_type(param.annotation),
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

    def _add_allowed_values(self, operator_name: str, parameters: List[Dict[str, Any]]) -> None:
        """Add allowed_values to parameters if known.

        Modifies parameters list in-place to add allowed_values for enum-like parameters.

        Args:
            operator_name: Name of the operator
            parameters: List of parameter dictionaries to modify
        """
        if operator_name not in self.KNOWN_ENUMS:
            return

        enum_map = self.KNOWN_ENUMS[operator_name]

        for param in parameters:
            param_name = param["name"]
            if param_name in enum_map:
                param["allowed_values"] = enum_map[param_name]

    def get_operators_info(self) -> Dict[str, Any]:
        """Get comprehensive metadata for all available operators.

        Returns information about each operator including name, description,
        parameters, and input format. Useful for building UI components that
        allow users to select operators for DAG construction.

        Returns:
            Dictionary with keys:
            - 'total_count': int - Total number of operators
            - 'operators': List[Dict] - List of operator metadata dictionaries

            Each operator dictionary contains:
            - 'name': str - Operator name (registry key)
            - 'class_name': str - CamelCase class name
            - 'description': str - Human-readable description
            - 'parameters': List[Dict] - Parameter information for run() method
            - 'return_type': str - Output type (always 'MetricTrace')
            - 'input_format': str - Input format description
            - (optional) 'allowed_values': List[str] - For enum-like parameters

        Example:
            >>> api = OperatorDiscoveryAPI()
            >>> info = api.get_operators_info()
            >>> print(info['total_count'])
            5
            >>> compare_op = info['operators'][0]
            >>> print(compare_op['parameters'][0]['allowed_values'])
            ['<', '<=', '>', '>=', '==', '!=']
        """
        operators_list = []

        for operator_name, operator_class in sorted(OPERATOR_MAPPING.items()):
            parameters = self._extract_run_parameters(operator_class)
            self._add_allowed_values(operator_name, parameters)

            operator_info = {
                "name": operator_name,
                "class_name": operator_class.__name__,
                "description": self._extract_description(operator_class),
                "parameters": parameters,
                "return_type": "MetricTrace",
                "output_type": self.KNOWN_OUTPUT_TYPES.get(operator_name),
                "input_format": "MetricTrace or List[MetricTrace]"
            }

            operators_list.append(operator_info)

        return {
            "total_count": len(operators_list),
            "operators": operators_list
        }

    def get_operator_info(self, operator_name: str) -> Dict[str, Any]:
        """Get metadata for a specific operator by name.

        Args:
            operator_name: Name of the operator (registry key)

        Returns:
            Dictionary with operator metadata

        Raises:
            ValueError: If operator not found
        """
        if operator_name not in OPERATOR_MAPPING:
            raise ValueError(f"Operator '{operator_name}' not found in registry")

        operator_class = OPERATOR_MAPPING[operator_name]
        parameters = self._extract_run_parameters(operator_class)
        self._add_allowed_values(operator_name, parameters)

        return {
            "name": operator_name,
            "class_name": operator_class.__name__,
            "description": self._extract_description(operator_class),
            "parameters": parameters,
            "return_type": "MetricTrace",
            "output_type": self.KNOWN_OUTPUT_TYPES.get(operator_name),
            "input_format": "MetricTrace or List[MetricTrace]"
        }

    def validate_operator_call(self, operator_name: str, **kwargs) -> bool:
        """Validate if operator can be called with given parameters.

        Args:
            operator_name: Name of the operator
            **kwargs: Parameters to validate

        Returns:
            bool: True if parameters are valid for the operator

        Raises:
            ValueError: If operator not found
        """
        if operator_name not in OPERATOR_MAPPING:
            raise ValueError(f"Operator '{operator_name}' not found")

        operator_class = OPERATOR_MAPPING[operator_name]
        sig = inspect.signature(operator_class.run)

        try:
            # Try to bind the parameters to the signature
            sig.bind(None, **kwargs)  # None for 'self'
            return True
        except TypeError:
            return False
