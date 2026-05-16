"""Path configuration for humex project directory structure.

This module defines standard paths for data, configuration, and output files
used throughout the humex framework.
"""

import os

# Base directory for the humex utils module
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Project root directory — use AVA_DATA_PATH env var when installed as a package
# (e.g. in Docker), otherwise derive from __file__ for local dev.
_env_data_path = os.environ.get("AVA_DATA_PATH")
if _env_data_path:
    PROJECT_ROOT = os.path.abspath(os.path.join(_env_data_path, ".."))
else:
    PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "../../.."))

# Standard directory paths for different data types
DATA_PATH = _env_data_path or os.path.join(PROJECT_ROOT, "data")  # Main data directory
LOGIC_PATH = os.path.join(DATA_PATH, "logic_cfg")                # Logic evaluation configurations
ANALYZER_PATH = os.path.join(DATA_PATH, "analyzer_cfg")          # Analysis pipeline configurations
DAG_CFG_PATH = os.path.join(DATA_PATH, "dag_cfg")                # DAG configuration examples
SCENARIO_PATH = os.path.join(DATA_PATH, "scenarios")             # Generated scenario data directory
CONVERTER_PATH = os.path.join(PROJECT_ROOT, "converters")        # Data format conversion utilities
SCENARIO_CONFIG = os.path.join(PROJECT_ROOT, "scenarios")        # Scenario configuration files for simulator
SCENARIO_DATA = os.path.join(DATA_PATH, "scenarios")             # Generated scenario data output

# Legacy compatibility
OUTPUT_PATH = DATA_PATH  # For backward compatibility

# Ensure paths end with separator for consistency
DATA_PATH = DATA_PATH + os.sep
OUTPUT_PATH = OUTPUT_PATH + os.sep
LOGIC_PATH = LOGIC_PATH + os.sep
ANALYZER_PATH = ANALYZER_PATH + os.sep
DAG_CFG_PATH = DAG_CFG_PATH + os.sep
SCENARIO_PATH = SCENARIO_PATH + os.sep
SCENARIO_DATA = SCENARIO_DATA + os.sep


# Helper functions for new results structure
def _resolve_scenario_folder(scenario_name: str) -> str:
    """Resolve scenario folder location. All scenarios are in data/scenarios/."""
    return f'{SCENARIO_DATA}{os.sep}{scenario_name}{os.sep}'


def get_scenario_folder(scenario_name):
    """Get the folder path for a specific scenario."""
    return _resolve_scenario_folder(scenario_name)

def get_scenario_file_path(scenario_name):
    """Get the scenario file path with proper naming convention."""
    return f'{get_scenario_folder(scenario_name)}ava_scenario_{scenario_name}.pb'

def get_map_file_path(scenario_name):
    """Get the map file path with proper naming convention."""
    return f'{get_scenario_folder(scenario_name)}ava_map_{scenario_name}.pb'

def get_signal_file_path(scenario_name):
    """Get the signal file path with proper naming convention."""
    return f'{get_scenario_folder(scenario_name)}ava_signal_{scenario_name}.pb'

def get_video_file_path(scenario_name):
    """Get the video file path with proper naming convention."""
    return f'{get_scenario_folder(scenario_name)}video_{scenario_name}.mp4'

def get_analyzer_result_file_path(scenario_name, analyzer_name):
    """Get the analyzer result file path with proper naming convention."""
    return f'{get_scenario_folder(scenario_name)}analyzer_result_{analyzer_name}_{scenario_name}.pb'

def get_metrics_result_file_path(scenario_name):
    """Get the metrics result file path with proper naming convention."""
    return f'{get_scenario_folder(scenario_name)}ava_metrics_result_{scenario_name}.proto'

def get_dag_yaml_file_path(scenario_name):
    """Get the DAG YAML file path with proper naming convention."""
    return f'{get_scenario_folder(scenario_name)}ava_dag_{scenario_name}.yaml'

def ensure_scenario_folder(scenario_name):
    """Ensure the scenario folder exists, create if it doesn't."""
    folder_path = _resolve_scenario_folder(scenario_name)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

# Debug output for path verification (commented out)
# print(LIBRARY)
