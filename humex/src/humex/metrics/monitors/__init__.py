import os
import importlib

monitor_mapping = {}

# Check both the monitors directory itself and the catalog subdirectory
module_dir = os.path.dirname(__file__)
catalog_dir = os.path.join(module_dir, 'catalog')

# Load monitors from catalog subdirectory if it exists
if os.path.exists(catalog_dir):
    for filename in os.listdir(catalog_dir):
        if filename.endswith(".py") and filename != "__init__.py" and not filename.startswith("_"):
            module_name = filename[:-3]  # Remove .py extension
            module = importlib.import_module(f"humex.metrics.monitors.catalog.{module_name}")

            # Please refer to README for class naming convention
            name = module_name.split('_')
            name = [word.capitalize() for word in name]
            class_name = ''.join(name)  # e.g., ego_collision -> EgoCollision
            cls = getattr(module, class_name)
            # Map by snake_case module name (existing behavior)
            monitor_mapping[module_name] = cls
            # Also map by CamelCase class name for convenience
            monitor_mapping[class_name] = cls

# Aliases: old/deprecated names → canonical monitor names
# This allows renaming monitors while keeping backward compatibility
# with existing YAML configs and saved metric definitions.
MONITOR_ALIASES = {
    "front_vehicle_distance_naive": "front_vehicle_distance",
    "FrontVehicleDistanceNaive": "FrontVehicleDistance",
    "front_vehicle_id_naive": "front_vehicle_id",
    "FrontVehicleIdNaive": "FrontVehicleId",
    "ego_speed_limit": "ego_lane_speed_limit",
    "EgoSpeedLimit": "EgoLaneSpeedLimit",
    "ego_lat_accel_ai": "ego_lat_accel",
    "EgoLatAccelAi": "EgoLatAccel",
    "ego_lon_accel_ai": "ego_lon_accel",
    "EgoLonAccelAi": "EgoLonAccel",
    "ego_lon_jerk_ai": "ego_lon_jerk",
    "EgoLonJerkAi": "EgoLonJerk",
    "lateral_distance_ai": "lateral_distance",
    "LateralDistanceAi": "LateralDistance",
    "time_headway_ai": "time_headway",
    "TimeHeadwayAi": "TimeHeadway",
}

# Register aliases — point old names to the canonical class
for alias, canonical in MONITOR_ALIASES.items():
    if canonical in monitor_mapping:
        monitor_mapping[alias] = monitor_mapping[canonical]
