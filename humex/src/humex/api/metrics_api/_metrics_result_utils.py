"""Private utility module for metrics result file handling.

Internal implementation details for saving and managing metrics result files.
Not intended for external use.
"""

import os
from datetime import datetime
from pathlib import Path


def get_metrics_result_file_path_with_timestamp(scenario_name: str, dag_or_analyzer_name: str) -> Path:
    """Generate metrics result file path with scenario name, DAG/analyzer name, and timestamp.

    Naming convention: ava_metrics_result_{scenario_name}_{dag_or_analyzer_name}_{datetime}.pb
    Datetime format: YYYYMMDDhhmmss (e.g., 20251130214905)

    Args:
        scenario_name: Name of the scenario being evaluated
        dag_or_analyzer_name: Name of the DAG or analyzer configuration

    Returns:
        Path object pointing to the metrics result file location

    Example:
        >>> path = get_metrics_result_file_path_with_timestamp("scenario3", "safety_basic_ai")
        >>> str(path)
        'data/scenarios/scenario3/ava_metrics_result_scenario3_safety_basic_ai_20251130214905.pb'
    """
    # Generate timestamp in YYYYMMDDhhmmss format
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Build scenario folder path (absolute, relative to humex project root)
    from humex.utils.paths import SCENARIO_DATA
    scenario_folder = Path(SCENARIO_DATA) / scenario_name

    # Ensure scenario folder exists
    scenario_folder.mkdir(parents=True, exist_ok=True)

    # Build full file path
    filename = f"ava_metrics_result_{scenario_name}_{dag_or_analyzer_name}_{timestamp}.pb"
    file_path = scenario_folder / filename

    return file_path
