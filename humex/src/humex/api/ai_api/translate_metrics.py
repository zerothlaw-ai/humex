"""Metrics translation API for converting requirements to YAML configurations."""

import json
import os
import yaml
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from humex.api.ai_api.models._claude_cli import ClaudeCLIModel
from humex.api.ai_api.models._qwen import QwenModel
from humex.metrics.dag.dag import MetricDAG


class TranslateMetrics:
    """Translate natural language requirements to metrics YAML configurations.

    This class converts natural language descriptions of safety and performance metrics
    into YAML configurations that can be used with humex's analyzer system. It combines
    system knowledge about monitors, operators, and DAG structure with user requirements
    to produce valid metric configurations.
    """

    def __init__(self, model: str = "claude_cli", qwen_model: Optional[str] = None):
        """Initialize TranslateMetrics with specified model.

        Loads system prompt about monitors, operators, and DAG structure.

        Args:
            model: Model to use for translation. Supports "claude_cli" (default) or "qwen".
            qwen_model: Ollama model name when using "qwen" (default: "qwen2.5:0.5b").
                       Examples: "qwen2.5:0.5b", "qwen2.5:7b", "qwen2.5-coder:7b"

        Raises:
            ValueError: If an unsupported model is specified
            FileNotFoundError: If system prompt file not found
        """
        if model not in ("claude_cli", "qwen"):
            raise ValueError(
                f"Unsupported model: {model}. Supported models: 'claude_cli', 'qwen'"
            )
        self.model = model
        self._qwen_instance = QwenModel(qwen_model) if model == "qwen" else None
        self.system_prompt = self._load_system_prompt()

    @staticmethod
    def _load_system_prompt() -> str:
        """Load system prompt from prompt file.

        Returns:
            System prompt content as string

        Raises:
            FileNotFoundError: If prompt file not found
        """
        prompt_file = Path(__file__).parent / "prompts" / "dag_preprompt.txt"

        if not prompt_file.exists():
            raise FileNotFoundError(
                f"System prompt file not found at: {prompt_file}\n"
                f"Expected file: src/humex/api/ai_api/prompts/dag_preprompt.txt"
            )

        with open(prompt_file, "r") as f:
            return f.read()

    @staticmethod
    def _generate_dag_name() -> str:
        """Generate a timestamp-based DAG name.

        Returns:
            DAG name in format: dag_YYYYMMDD_HHMMSS
        """
        return datetime.now().strftime("dag_%Y%m%d_%H%M%S")

    @staticmethod
    def _extract_yaml_and_feedback(raw_response: str) -> Tuple[str, str]:
        """Extract YAML and feedback from LLM response.

        Separates markdown code blocks containing YAML from explanatory text
        and feedback messages provided by the LLM.

        Patterns:
        - Some explanation ```yaml YAML content ``` More explanation

        Args:
            raw_response: Complete LLM response (may include explanation + YAML)

        Returns:
            Tuple of (yaml_content, feedback_message)
        """
        # Find markdown code block boundaries
        first_fence = raw_response.find("```")

        # If no markdown block found, all is feedback
        if first_fence == -1:
            return "", raw_response

        # Find the closing fence after the opening fence (not the last one in entire response)
        # Start searching after the opening fence
        last_fence = raw_response.find("```", first_fence + 3)

        # If no closing fence found, treat all as feedback
        if last_fence == -1:
            return "", raw_response

        # Extract feedback before and after YAML
        feedback_before = raw_response[:first_fence].strip()
        feedback_after = raw_response[last_fence + 3:].strip()
        feedback = "\n\n".join(filter(None, [feedback_before, feedback_after]))

        # Extract YAML (between fences)
        yaml_start = first_fence + 3
        # Skip the opening fence line (it may have ```yaml or just ```)
        newline_pos = raw_response.find("\n", yaml_start)
        if newline_pos != -1:
            yaml_start = newline_pos + 1
        # else keep yaml_start as first_fence + 3

        yaml_content = raw_response[yaml_start:last_fence].strip()

        return yaml_content, feedback

    @staticmethod
    def _validate_yaml(yaml_content: str) -> Dict[str, Any]:
        """Validate YAML content and return parsed dictionary.

        Args:
            yaml_content: YAML string to validate (should be extracted YAML, not markdown)

        Returns:
            Parsed YAML as dictionary (or empty dict if YAML is None/empty)

        Raises:
            ValueError: If YAML is invalid
        """
        try:
            parsed = yaml.safe_load(yaml_content)
            # If parsed is None, return empty dict
            if parsed is None:
                return {}
            # If it's a dict, return it
            if isinstance(parsed, dict):
                return parsed
            # For other types, wrap in a dict with content key
            return {"content": parsed}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to validate YAML: {str(e)}")

    def translate(
        self,
        requirement: str,
        dag_name: Optional[str] = None,
        save_yaml: bool = False,
        save_visualization: bool = False,
        visualization_format: str = "png",
        config_type: str = "auto",
        prompt_context: Optional[str] = None,
        visualize: bool = False
    ) -> Dict[str, Any]:
        """Translate natural language requirement to metrics YAML configuration.

        Converts natural language descriptions of metrics or analysis requirements
        into DAG YAML configurations. Optionally saves the generated YAML to data/dag_cfg
        and generates visualization. Returns both the generated YAML and LLM feedback.

        The system prompt (monitors, operators, DAG structure) is automatically
        combined with the user's requirement to provide complete context to the LLM.

        Args:
            requirement: Natural language description of the metric or DAG requirement.
                        Example: "Check if ego vehicle exceeds speed limit of 30 mph"
            dag_name: Optional name for saving files. If not provided and saving is enabled,
                     auto-generates a timestamp-based name (dag_YYYYMMDD_HHMMSS).
            save_yaml: Whether to save generated YAML to data/dag_cfg folder (default: False)
            save_visualization: Whether to generate PNG visualization (default: False)
            visualization_format: Image format for visualization: "png", "svg", or "pdf" (default: "png")
            config_type: Type of configuration to generate: "analyzer", "logic", or "auto"
                        (default: "auto" - LLM determines the most appropriate type)
            prompt_context: Optional additional context to append to system prompt.
                           Useful for overriding or augmenting system knowledge.
            visualize: Whether to generate DAG visualization (default: False).
                      If True, visualization is saved to system temp directory (or data/dag_cfg if save_yaml=True).
                      Uses visualization_format for output format.

        Returns:
            Dictionary with keys:
            - 'yaml_content': str - Generated DAG YAML (always provided)
            - 'feedback': str - LLM explanations and feedback messages
            - 'dag_yaml_path': Optional[str] - Path to saved YAML file, or None if not saved
            - 'dag_visualization_path': Optional[str] - Path to visualization image (PNG/SVG/PDF), or None if visualize=False
                                        When visualize=True and save_yaml=False, path is in system temp directory
                                        When visualize=True and save_yaml=True, path is in data/dag_cfg
            - 'dag_name': Optional[str] - Name used for saving files
            - 'num_nodes': Optional[int] - Number of nodes in DAG (if parseable)
            - 'num_edges': Optional[int] - Number of edges in DAG (if parseable)

        Raises:
            ValueError: If YAML validation fails or model is unsupported
            FileNotFoundError: If Claude CLI is not installed
            Exception: If the model call fails

        Example:
            >>> translator = TranslateMetrics()
            >>> result = translator.translate("Check if vehicle stays in lane")
            >>> print(result['yaml_content'])  # YAML only
            >>> print(result['feedback'])      # LLM explanation

            >>> result = translator.translate(
            ...     "Check speed limit",
            ...     dag_name="speed_check",
            ...     save_yaml=True,
            ...     save_visualization=True
            ... )
            >>> print(result['dag_yaml_path'])  # data/dag_cfg/speed_check.yaml
            >>> print(result['dag_visualization_path'])  # data/dag_cfg/speed_check.png
        """
        # 1. Get latest monitor and operator information from discovery APIs
        from humex.api.metrics_api import MonitorDiscoveryAPI, OperatorDiscoveryAPI

        monitors_info = MonitorDiscoveryAPI().get_monitors_info()
        operators_info = OperatorDiscoveryAPI().get_operators_info()

        # Convert to JSON for inclusion in prompt
        monitors_json = json.dumps(monitors_info, indent=2)
        operators_json = json.dumps(operators_info, indent=2)

        # 2. Build combined prompt: system + monitors + operators + context + requirement
        full_prompt = self.system_prompt

        full_prompt += "\n\n## AVAILABLE MONITORS\n\n"
        full_prompt += monitors_json

        full_prompt += "\n\n## AVAILABLE OPERATORS\n\n"
        full_prompt += operators_json

        if prompt_context:
            full_prompt += f"\n\n## ADDITIONAL CONTEXT\n\n{prompt_context}"

        full_prompt += f"\n\n## USER REQUIREMENT\n\nPlease translate the following requirement into an appropriate metrics configuration:\n\n{requirement}\n\nGenerate only valid YAML. The configuration should use the DAG format with monitor, operator, and comparison nodes."
        # print('hello')
        # print(full_prompt)
        # 3. Call LLM to generate YAML
        if self.model == "claude_cli":
            raw_response = ClaudeCLIModel.translate_metrics(full_prompt)
        elif self.model == "qwen":
            raw_response = self._qwen_instance.translate_metrics(full_prompt)
        else:
            raise ValueError(
                f"Unsupported model: {self.model}. Supported models: 'claude_cli', 'qwen'"
            )

        # 4. Extract YAML and feedback from LLM response
        yaml_content, feedback = self._extract_yaml_and_feedback(raw_response)

        # 5. Validate YAML
        try:
            parsed_yaml = self._validate_yaml(yaml_content)
        except ValueError as e:
            raise ValueError(f"LLM returned invalid YAML: {str(e)}")

        # 6. Initialize result dictionary
        result = {
            "yaml_content": yaml_content,
            "feedback": feedback,
            "dag_yaml_path": None,
            "dag_visualization_path": None,
            "dag_name": dag_name,
            "num_nodes": None,
            "num_edges": None,
        }

        # 7. If saving or visualization requested, ensure dag_name and create directory
        if save_yaml or save_visualization or visualize:
            if dag_name is None:
                dag_name = self._generate_dag_name()
                result["dag_name"] = dag_name

            dag_cfg_path = Path(__file__).parent.parent.parent.parent.parent / "data" / "dag_cfg"
            os.makedirs(dag_cfg_path, exist_ok=True)

            # 8. Save YAML file if requested
            if save_yaml:
                yaml_file_path = dag_cfg_path / f"{dag_name}.yaml"
                try:
                    with open(yaml_file_path, "w") as f:
                        f.write(yaml_content)
                    result["dag_yaml_path"] = str(yaml_file_path)
                except Exception as e:
                    raise ValueError(f"Failed to save YAML file: {str(e)}")

            # 9. Generate visualization if requested via save_visualization (legacy)
            if save_visualization:
                try:
                    from humex.api.metrics_api import VisualizeDagAPI

                    if not save_yaml:
                        # Need to save YAML temporarily to visualize
                        yaml_file_path = dag_cfg_path / f"{dag_name}.yaml"
                        with open(yaml_file_path, "w") as f:
                            f.write(yaml_content)
                        result["dag_yaml_path"] = str(yaml_file_path)

                    viz_api = VisualizeDagAPI()
                    viz_result = viz_api.visualize(
                        dag_yaml_path=str(yaml_file_path),
                        output_format=visualization_format,
                        scenario_name=dag_name,
                        view=False
                    )
                    result["dag_visualization_path"] = viz_result["dag_visualization_path"]
                except ImportError:
                    print("Warning: graphviz package not installed, skipping visualization")
                except Exception as e:
                    print(f"Warning: Failed to generate visualization: {str(e)}")

            # 10. Generate visualization if requested via visualize parameter
            if visualize:
                try:
                    from humex.api.metrics_api import VisualizeDagAPI

                    # Determine YAML path: use saved path if available, otherwise use temp
                    if save_yaml:
                        # Use already saved YAML
                        yaml_file_path = dag_cfg_path / f"{dag_name}.yaml"
                    else:
                        # Create temporary YAML file in system temp directory
                        temp_dir = Path(tempfile.gettempdir())
                        temp_yaml_file = temp_dir / f"ava_dag_{dag_name}.yaml"
                        with open(temp_yaml_file, "w") as f:
                            f.write(yaml_content)
                        yaml_file_path = temp_yaml_file

                    # Generate visualization using VisualizeDagAPI
                    viz_api = VisualizeDagAPI()
                    viz_result = viz_api.visualize(
                        dag_yaml_path=str(yaml_file_path),
                        output_format=visualization_format,
                        scenario_name=dag_name,
                        view=False
                    )
                    result["dag_visualization_path"] = viz_result["dag_visualization_path"]

                    # Clean up temporary YAML if it was created for visualization only
                    if not save_yaml and yaml_file_path.exists():
                        try:
                            yaml_file_path.unlink()
                        except Exception as e:
                            # Don't fail if cleanup fails, just log warning
                            pass

                except ImportError:
                    print("Warning: graphviz package not installed, skipping visualization")
                except Exception as e:
                    print(f"Warning: Failed to generate visualization: {str(e)}")

        # 11. Try to extract node and edge counts from parsed YAML
        try:
            if "nodes" in parsed_yaml:
                result["num_nodes"] = len(parsed_yaml["nodes"])
                # Count edges: sum of all input arrays
                result["num_edges"] = sum(
                    len(node.get("inputs", [])) for node in parsed_yaml["nodes"].values()
                )
        except Exception:
            pass  # Unable to parse structure, leave counts as None

        return result
