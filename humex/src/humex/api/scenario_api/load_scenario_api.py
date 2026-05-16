"""Scenario API for loading and preparing scenarios.

This module provides a unified interface for loading scenarios from various sources:
- Individual proto files on disk
- A scenario folder (auto-discovers proto files)
- In-memory protobuf objects (gRPC compatibility)

All loading paths converge on load_from_proto_objects() which is the core building method.
"""

import os
from pathlib import Path
from typing import Optional

from humex.proto import scenario_pb2 as scenario_data_pb2

from ...components.scenario import Scenario
from ...components.statepoint import StatePoint
from ...components.object import Object
from ...hmap.road_map import RoadMap
from ...hmap.road_map_loader import RoadMapLoader
from ...utils.paths import get_scenario_folder, get_scenario_file_path, get_map_file_path, get_signal_file_path
from ...utils.timestamp import to_ns


class ScenarioAPI:
    """API for loading and preparing scenarios from various sources.

    This class provides a unified interface for loading scenarios with support for
    three input modes:
    1. From individual proto files (scenario_data.proto, map.proto, optional signal.proto)
    2. From a scenario folder (auto-discovers proto files)
    3. From in-memory protobuf objects (for gRPC services)

    All loading methods converge on load_from_proto_objects() which is the core method
    that handles all actual scenario building logic.
    """

    def load_from_proto_files(
        self,
        scenario_file_path: str,
        map_file_path: str,
        signal_file_path: Optional[str] = None,
        enhance: bool = True,
        lane_map_file_path: Optional[str] = None,
        role_file_path: Optional[str] = None,
        frequency: Optional[float] = None,
    ) -> Scenario:
        """Load scenario from individual proto files on disk.

        Args:
            scenario_file_path: Path to scenario_data.proto file
            map_file_path: Path to map.proto file
            signal_file_path: Path to signal.proto file (optional)
            enhance: If True, calculate velocity and acceleration vectors
            lane_map_file_path: Optional path to lane_map.pb sidecar built
                during conversion-task Stage 2. When present, the deserialized
                LaneMap is wrapped together with the legacy RoadMap into an
                ``HMap`` facade and assigned to ``scenario.map`` —
                lane queries on ``scenario.map`` then route to LaneMap v2.
            role_file_path: Optional path to role.pb sidecar (per-frame
                front/rear precomputed by :func:`role_table_builder`). When
                present, attached as ``scenario.role_table``; monitors
                short-circuit to it.
            frequency: Optional target sampling rate (Hz). When set and
                differs from the source, all object trajectories are
                resampled (linear interpolation) onto a new frame grid at
                this rate before enhancement, so velocity/accel are
                recomputed on the resampled grid. Duration is preserved.

        Returns:
            Scenario: Internal Scenario object with frames and objects

        Raises:
            FileNotFoundError: If required files don't exist
            Exception: If protobuf deserialization fails
        """
        # Validate files exist
        if not os.path.isfile(scenario_file_path):
            raise FileNotFoundError(f"Scenario file not found: {scenario_file_path}")
        if not os.path.isfile(map_file_path):
            raise FileNotFoundError(f"Map file not found: {map_file_path}")

        print(f"Loading scenario from files: {scenario_file_path}")

        # Deserialize scenario protobuf
        print(f"Deserializing scenario protobuf from: {scenario_file_path}")
        scenario_pb = scenario_data_pb2.ScenarioData()
        with open(scenario_file_path, "rb") as f:
            scenario_pb.ParseFromString(f.read())

        # Load map (try protobuf first, then JSON)
        print(f"Loading map from: {map_file_path}")
        try:
            map_data = RoadMapLoader.from_file(map_file_path, format_type="protobuf")
            print(f"Loaded map in protobuf format")
        except (FileNotFoundError, Exception) as e:
            # Try JSON format with .json extension
            json_map_path = map_file_path.replace(".pb", ".json")
            try:
                map_data = RoadMapLoader.from_file(json_map_path, format_type="json")
                print(f"Loaded map in JSON format")
            except (FileNotFoundError, Exception) as e2:
                raise FileNotFoundError(
                    f"Could not load map from {map_file_path} in protobuf or JSON format. "
                    f"Protobuf error: {e}, JSON error: {e2}"
                )

        # Load signal (optional)
        signal_data = None
        if signal_file_path and os.path.isfile(signal_file_path):
            try:
                signal_data = RoadMapLoader.load_signal_file(signal_file_path)
                print(f"Loaded signal data from: {signal_file_path}")
            except Exception as e:
                print(f"Warning: Failed to load signal data: {e}")

        # Delegate to load_from_proto_objects (the core method)
        scenario = self.load_from_proto_objects(
            scenario_pb, map_data, signal_data, enhance=enhance, frequency=frequency
        )

        # Auto-discover lane_map.pb and role.pb in the scenario's directory
        # when the caller didn't explicitly pass paths. Most call sites
        # (evaluation, metric eval, scenario import) provide just
        # scenario.pb / map.pb and don't know about the sidecars; we pick
        # them up automatically so monitors can short-circuit through
        # role_table / HMap.
        scenario_dir = os.path.dirname(scenario_file_path)
        if lane_map_file_path is None:
            candidate = os.path.join(scenario_dir, "lane_map.pb")
            if os.path.isfile(candidate):
                lane_map_file_path = candidate
        if role_file_path is None:
            candidate = os.path.join(scenario_dir, "role.pb")
            if os.path.isfile(candidate):
                role_file_path = candidate

        # Attach lane_map sidecar when present and wrap scenario.map in the
        # HMap facade so all lane queries route through LaneMap v2.
        # When lane_map.pb is missing, scenario.map stays as the raw RoadMap
        # and lane queries fall back to the legacy KDTree (less accurate;
        # warn loudly and point the user at the conversion-task regenerate).
        if lane_map_file_path and os.path.isfile(lane_map_file_path):
            try:
                from humex.proto import lane_map_pb2
                from humex.hmap.lane_map import LaneMap
                from humex.hmap.hmap import HMap

                lm_pb = lane_map_pb2.LaneMapData()
                with open(lane_map_file_path, "rb") as f:
                    lm_pb.ParseFromString(f.read())
                lane_map_obj = LaneMap.from_proto(lm_pb)
                # Wrap (legacy_map, lane_map) into the unified facade and
                # replace scenario.map. RoadMap-specific helpers
                # (load_signals, query_*, get_segments, etc.) keep working
                # via __getattr__ passthrough.
                scenario.map = HMap(scenario.map, lane_map_obj)
                print(f"Loaded lane_map (algorithm={lane_map_obj.algorithm_version}) from: {lane_map_file_path}")
            except Exception as e:
                print(f"Warning: Failed to load lane_map: {e}")
        else:
            print(
                "Warning: no lane_map.pb supplied; scenario.map will use legacy "
                "RoadMap lane queries. For Hume scenarios, re-run conversion or "
                "POST regenerate_subtask_asset(asset='lane_map')."
            )

        # Attach role.pb sidecar when present. Failure to load is non-fatal —
        # monitors fall back to the slow path when role_table is None.
        if role_file_path and os.path.isfile(role_file_path):
            try:
                from humex.proto import role_pb2
                from humex.hmap.role_table import RoleTable

                rt_pb = role_pb2.RoleTable()
                with open(role_file_path, "rb") as f:
                    rt_pb.ParseFromString(f.read())
                scenario.role_table = RoleTable.from_proto(rt_pb)
                print(
                    f"Loaded role_table (algorithm={scenario.role_table.algorithm_version}, "
                    f"frames={scenario.role_table.frame_count}) from: {role_file_path}"
                )
            except Exception as e:
                print(f"Warning: Failed to load role_table: {e}")

        return scenario

    def load_from_folder(
        self,
        scenario_folder_path: str,
        enhance: bool = True
    ) -> Scenario:
        """Load scenario from a folder with auto-discovered proto files.

        Scans the folder for standard naming patterns:
        - scenario.pb or ava_scenario_* or scenario_*.pb (scenario file)
        - map.pb or ava_map_* or map_*.pb (map file)
        - signal.pb or ava_signal_* or signal_*.pb (signal file, optional)

        Args:
            scenario_folder_path: Path to folder containing scenario proto files
            enhance: If True, calculate velocity and acceleration vectors

        Returns:
            Scenario: Internal Scenario object with frames and objects

        Raises:
            FileNotFoundError: If required files not found in folder
            ValueError: If folder doesn't exist
        """
        folder_path = Path(scenario_folder_path)

        if not folder_path.is_dir():
            raise ValueError(f"Scenario folder not found: {scenario_folder_path}")

        print(f"Loading scenario from folder: {scenario_folder_path}")

        # Find scenario file
        scenario_file = self._find_file_in_folder(folder_path, ["scenario.pb", "ava_scenario_*", "scenario_*.pb"])
        if not scenario_file:
            raise FileNotFoundError(f"No scenario file found in {scenario_folder_path}")

        # Find map file
        map_file = self._find_file_in_folder(folder_path, ["map.pb", "ava_map_*", "map_*.pb"])
        if not map_file:
            raise FileNotFoundError(f"No map file found in {scenario_folder_path}")

        # Find signal file (optional)
        signal_file = self._find_file_in_folder(folder_path, ["signal.pb", "ava_signal_*", "signal_*.pb"])

        # Find lane_map / role sidecars (optional)
        lane_map_file = self._find_file_in_folder(folder_path, ["lane_map.pb"])
        role_file = self._find_file_in_folder(folder_path, ["role.pb"])

        print(f"Auto-discovered: scenario={scenario_file.name}, map={map_file.name}")
        if signal_file:
            print(f"Auto-discovered: signal={signal_file.name}")
        if lane_map_file:
            print(f"Auto-discovered: lane_map={lane_map_file.name}")
        if role_file:
            print(f"Auto-discovered: role={role_file.name}")

        # Delegate to load_from_proto_files
        return self.load_from_proto_files(
            str(scenario_file),
            str(map_file),
            str(signal_file) if signal_file else None,
            enhance=enhance,
            lane_map_file_path=str(lane_map_file) if lane_map_file else None,
            role_file_path=str(role_file) if role_file else None,
        )

    def load_from_proto_objects(
        self,
        scenario_data_pb,
        map_data_pb,
        signal_data_pb=None,
        enhance: bool = True,
        frequency: Optional[float] = None,
    ) -> Scenario:
        """Load scenario from in-memory protobuf objects (core method).

        This is the authoritative method where all actual scenario building happens.
        All other loading methods (load_from_proto_files, load_from_folder) delegate
        to this method after handling their respective input sources.

        Args:
            scenario_data_pb: Scenario protobuf message (scenario_pb2.ScenarioData)
            map_data_pb: Map data protobuf
            signal_data_pb: Signal protobuf message (optional)
            enhance: If True, calculate velocity and acceleration vectors
            frequency: Optional target sampling rate (Hz). When set and
                differs from ``scenario_data_pb.frequency``, the scenario
                proto is resampled onto a new frame grid at this rate
                before the Scenario is built.

        Returns:
            Scenario: Internal Scenario object with frames and objects

        Raises:
            ValueError: If required protobuf objects are None or invalid
        """
        if scenario_data_pb is None:
            raise ValueError("scenario_data_pb cannot be None")
        if map_data_pb is None:
            raise ValueError("map_data_pb cannot be None")

        print(f"Loading scenario from protobuf objects")

        # Resample frames to the requested frequency before building the
        # Scenario. Duration stays constant; frame count = duration*frequency.
        # When ``enhance=True`` runs later, velocity/accel are recomputed on
        # the resampled grid automatically.
        if frequency is not None and frequency > 0 and frequency != scenario_data_pb.frequency:
            print(
                f"Resampling scenario {scenario_data_pb.frequency} Hz → {frequency} Hz"
            )
            scenario_data_pb = self._resample_scenario_pb(scenario_data_pb, frequency)

        # Extract scenario name from protobuf
        scenario_name = getattr(scenario_data_pb, "map_name", "unknown")

        # === CORE BUILDING LOGIC (formerly in _build_scenario) ===

        # 1. Create RoadMap from map data
        scenario = self._create_scenario(scenario_data_pb, map_data_pb, scenario_name)

        # 2. Load all object definitions into roster
        self._load_roster(scenario, scenario_data_pb)

        # 3. Load all frames and statepoints information
        self._load_frames_and_statepoints(scenario, scenario_data_pb)

        # 4. Keep all frames (including empty ones) to preserve duration/frequency
        # Note: Empty frames allow scenarios to maintain full timeline even when
        # vehicles only exist for part of the simulation
        # Previously: self._cleanup_empty_frames(scenario)

        # 5. Attach signal data if provided
        if signal_data_pb is not None:
            self._attach_signals(scenario, signal_data_pb)

        # 6. Last resort: Auto-assign ego based on frequency
        if scenario.ego_id is None:
            scenario.assign_ego_id()

        print(f"Scenario loaded with {len(scenario.frames)} frames")

        # 7. Optionally enhance with kinematics
        if enhance:
            scenario = self._enhance_scenario(scenario)

        return scenario

    def _create_scenario(
        self,
        scenario_pb,
        map_data_pb,
        scenario_name: str
    ) -> Scenario:
        """Create the core Scenario and RoadMap objects.

        Args:
            scenario_pb: Scenario protobuf message
            map_data_pb: Map data protobuf
            scenario_name: Name for the scenario

        Returns:
            Scenario: Created scenario object with map attached
        """
        # Create RoadMap from map data
        print("Creating Ava Map")
        road_map = RoadMap(scenario_name)
        road_map.map_data = map_data_pb

        # Create Scenario
        print("Creating Ava Scenario")
        # Read ego_id from protobuf (primary source)
        ego_id = scenario_pb.ego_id if scenario_pb.ego_id != 0 else None
        scenario = Scenario(
            duration=scenario_pb.duration,
            frequency=scenario_pb.frequency,
            map_obj=road_map,
            ego_id=ego_id
        )
        scenario.scenario_name = scenario_pb.map_name  # Store scenario name for results

        return scenario

    def _load_roster(self, scenario: Scenario, scenario_pb) -> None:
        """Load all object definitions into scenario roster.

        Args:
            scenario: Scenario to populate
            scenario_pb: Scenario protobuf message
        """
        for obj_id, obj in scenario_pb.roster.items():
            obj_instance = Object(
                obj_id=int(obj_id),
                length=obj.length,
                width=obj.width,
                height=obj.height,
                is_ego=obj.is_ego,
                scenario=scenario
            )
            scenario.add_obj_to_roster(obj_instance)

        # Set ego_id from roster if not already set from protobuf top-level field
        if scenario.ego_id is None:
            for obj_id, obj in scenario_pb.roster.items():
                if obj.is_ego:
                    scenario.ego_id = int(obj_id)
                    break

        print(f"Roster created with {len(scenario_pb.roster)} objects")

    def _load_frames_and_statepoints(self, scenario: Scenario, scenario_pb) -> None:
        """Load all frames and statepoints information into scenario.

        Args:
            scenario: Scenario to populate
            scenario_pb: Scenario protobuf message
        """
        for ts, frame_data in scenario_pb.frames.items():
            # Skip empty frames (backward compatibility)
            if len(frame_data.obj_list) == 0:
                continue

            # Handle backward compatibility: convert float seconds to int64 nanoseconds if needed
            # Old .pb files/JSON have float timestamps in seconds; new ones have int64 in nanoseconds
            if isinstance(ts, str):
                # String format - determine if seconds or nanoseconds based on format
                ts_numeric = float(ts)

                # If string contains decimal point, it's in seconds format (e.g., '7.99993')
                # If it's a large integer-like value, it's in nanoseconds (e.g., '33333333')
                if '.' in ts:
                    # Seconds format - convert to nanoseconds
                    ts_int64 = to_ns(ts_numeric)
                elif ts_numeric > 1e8:
                    # Large value without decimal - likely nanoseconds (e.g., 100000000 = 0.1s)
                    ts_int64 = int(ts_numeric)
                else:
                    # Small integer value - could be either, try both
                    ts_as_ns = int(ts_numeric)
                    if ts_as_ns in scenario.frames:
                        ts_int64 = ts_as_ns
                    else:
                        # Try as seconds converted to nanoseconds
                        ts_as_seconds = to_ns(ts_numeric)
                        if ts_as_seconds in scenario.frames:
                            ts_int64 = ts_as_seconds
                        else:
                            # Default: assume nanoseconds (new format)
                            ts_int64 = ts_as_ns
            elif isinstance(ts, float):
                # Old format: float seconds - convert to int64 nanoseconds
                ts_int64 = to_ns(ts)
            else:
                # New format: already int64 nanoseconds
                ts_int64 = int(ts)

            frame = scenario.get_frame_by_ts(ts_int64)
            for obj_id, obj_data in frame_data.obj_list.items():
                new_obj = scenario.get_obj_copy_from_roster(int(obj_id))
                point = obj_data.sp
                position = (point.position.x, point.position.y, point.position.z)
                heading = (point.heading.roll, point.heading.pitch, point.heading.yaw)
                velocity = (point.velocity.x, point.velocity.y, point.velocity.z)
                acceleration = (point.acceleration.x, point.acceleration.y, point.acceleration.z)
                sp = StatePoint(obj_id=obj_id, position=position, heading=heading,
                                velocity=velocity, acceleration=acceleration)
                new_obj.update_mutable(sp)

                # Fallback: Check frame-level is_ego for backward compatibility with old protobuf files
                if scenario.ego_id is None and obj_data.is_ego:
                    new_obj.is_ego = obj_data.is_ego
                    scenario.ego_id = obj_id
                scenario.add_obj_to_frame(new_obj, frame)

    def _cleanup_empty_frames(self, scenario: Scenario) -> None:
        """Remove empty frames from scenario after loading.

        Args:
            scenario: Scenario to clean up
        """
        empty_timestamps = [ts for ts, frame in scenario.frames.items() if len(frame.obj_list) == 0]
        for ts in empty_timestamps:
            del scenario.frames[ts]
            if ts in scenario.timestamps:
                scenario.timestamps.remove(ts)

    def _attach_signals(self, scenario: Scenario, signal_data) -> None:
        """Attach signal data to scenario's map.

        Args:
            scenario: Scenario to attach signals to
            signal_data: Signal data protobuf
        """
        scenario.map.load_signals(signal_data)

    def scenario_to_proto(self, scenario) -> scenario_data_pb2.ScenarioData:
        """Serialize an humex Scenario object back to a ScenarioData protobuf.

        Args:
            scenario: Internal Scenario object with frames and objects

        Returns:
            ScenarioData protobuf message
        """
        data = scenario_data_pb2.ScenarioData()
        data.duration = scenario.duration
        data.frequency = scenario.frequency
        data.map_name = getattr(scenario, 'scenario_name', '') or getattr(scenario, 'map_name', '') or ''
        data.ego_id = scenario.ego_id or 0

        # Export roster
        for obj_id, obj in scenario.roster.items():
            new_obj = data.roster[obj_id]
            new_obj.id = obj.id
            new_obj.length, new_obj.width, new_obj.height = obj.length, obj.width, obj.height
            new_obj.is_ego = obj.is_ego

        # Export frames
        for ts, frame in scenario.frames.items():
            new_frame = data.frames[str(ts)]
            new_frame.timestamp = ts

            for obj_id, obj in frame.obj_list.items():
                new_obj = new_frame.obj_list[obj_id]
                new_obj.sp.position.x, new_obj.sp.position.y, new_obj.sp.position.z = (
                    obj.sp.position.x, obj.sp.position.y, obj.sp.position.z
                )
                new_obj.sp.velocity.x, new_obj.sp.velocity.y, new_obj.sp.velocity.z = (
                    obj.sp.velocity.x, obj.sp.velocity.y, obj.sp.velocity.z
                )
                new_obj.sp.heading.roll, new_obj.sp.heading.pitch, new_obj.sp.heading.yaw = (
                    obj.sp.heading.roll, obj.sp.heading.pitch, obj.sp.heading.yaw
                )
                new_obj.sp.acceleration.x, new_obj.sp.acceleration.y, new_obj.sp.acceleration.z = (
                    obj.sp.acceleration.x, obj.sp.acceleration.y, obj.sp.acceleration.z
                )

        return data

    def _enhance_scenario(self, scenario: Scenario) -> Scenario:
        """Calculate velocity and acceleration vectors for all objects.

        Applies kinematic enhancements to the scenario:
        - Velocity vectors calculated from consecutive positions
        - Acceleration vectors calculated from consecutive velocities

        Args:
            scenario: Scenario to enhance

        Returns:
            Scenario: Enhanced scenario with velocity and acceleration data
        """
        from ...convert.enhance import enhance_scenario

        return enhance_scenario(scenario)

    @staticmethod
    def _resample_scenario_pb(scenario_pb, new_frequency: float):
        """Return a new ScenarioData proto resampled to ``new_frequency``.

        Linearly interpolates each object's position/heading/velocity onto a
        new frame grid while preserving the source duration. Objects that are
        only visible during part of the source scenario are kept visible only
        across the corresponding span in the resampled output. The downstream
        ``_enhance_scenario`` step recomputes velocity/accel from the new
        positions, so velocity here is just a best-effort initialization.
        """
        import math

        from humex.proto import scenario_pb2 as scenario_data_pb2

        new_pb = scenario_data_pb2.ScenarioData()
        new_pb.frequency = new_frequency
        new_pb.duration = scenario_pb.duration
        new_pb.map_name = scenario_pb.map_name
        new_pb.ego_id = scenario_pb.ego_id
        for obj_id, obj in scenario_pb.roster.items():
            new_pb.roster[obj_id].CopyFrom(obj)

        # Per-object timeline of source statepoints, sorted by timestamp.
        per_obj: dict = {}
        for frame in scenario_pb.frames.values():
            for obj_id, obj in frame.obj_list.items():
                per_obj.setdefault(obj_id, []).append((frame.timestamp, obj))
        for obj_id in per_obj:
            per_obj[obj_id].sort(key=lambda pair: pair[0])

        new_interval_ns = int(round(1e9 / new_frequency))
        new_frame_count = int(math.floor(scenario_pb.duration * new_frequency))

        for i in range(new_frame_count):
            ts_ns = i * new_interval_ns
            new_frame = new_pb.frames[str(ts_ns)]
            new_frame.frame_id = i
            new_frame.timestamp = ts_ns
            for obj_id, timeline in per_obj.items():
                # Skip objects whose visibility span doesn't cover this ts.
                if ts_ns < timeline[0][0] or ts_ns > timeline[-1][0]:
                    continue
                lo_idx = 0
                hi_idx = len(timeline) - 1
                while lo_idx + 1 < hi_idx:
                    mid = (lo_idx + hi_idx) // 2
                    if timeline[mid][0] <= ts_ns:
                        lo_idx = mid
                    else:
                        hi_idx = mid
                lo_ts, lo_obj = timeline[lo_idx]
                hi_ts, hi_obj = timeline[hi_idx]
                if hi_ts == lo_ts:
                    alpha = 0.0
                else:
                    alpha = (ts_ns - lo_ts) / (hi_ts - lo_ts)

                interp = new_frame.obj_list[obj_id]
                interp.id = lo_obj.id
                interp.length = lo_obj.length
                interp.width = lo_obj.width
                interp.height = lo_obj.height
                interp.is_ego = lo_obj.is_ego
                interp.object_type = lo_obj.object_type
                sp = interp.sp
                sp.position.x = lo_obj.sp.position.x + alpha * (hi_obj.sp.position.x - lo_obj.sp.position.x)
                sp.position.y = lo_obj.sp.position.y + alpha * (hi_obj.sp.position.y - lo_obj.sp.position.y)
                sp.position.z = lo_obj.sp.position.z + alpha * (hi_obj.sp.position.z - lo_obj.sp.position.z)
                sp.velocity.x = lo_obj.sp.velocity.x + alpha * (hi_obj.sp.velocity.x - lo_obj.sp.velocity.x)
                sp.velocity.y = lo_obj.sp.velocity.y + alpha * (hi_obj.sp.velocity.y - lo_obj.sp.velocity.y)
                sp.velocity.z = lo_obj.sp.velocity.z + alpha * (hi_obj.sp.velocity.z - lo_obj.sp.velocity.z)
                sp.heading.roll = lo_obj.sp.heading.roll + alpha * (hi_obj.sp.heading.roll - lo_obj.sp.heading.roll)
                sp.heading.pitch = lo_obj.sp.heading.pitch + alpha * (hi_obj.sp.heading.pitch - lo_obj.sp.heading.pitch)
                # Yaw: handle ±π wrap by picking the shorter angular path.
                d_yaw = hi_obj.sp.heading.yaw - lo_obj.sp.heading.yaw
                if d_yaw > math.pi:
                    d_yaw -= 2 * math.pi
                elif d_yaw < -math.pi:
                    d_yaw += 2 * math.pi
                sp.heading.yaw = lo_obj.sp.heading.yaw + alpha * d_yaw

        return new_pb

    @staticmethod
    def _find_file_in_folder(folder_path: Path, patterns: list) -> Optional[Path]:
        """Find file in folder matching any of the given patterns.

        Args:
            folder_path: Path object pointing to folder
            patterns: List of glob patterns to match (e.g., ["ava_scenario_*", "ava_map_*"])

        Returns:
            Path to first matching file, or None if no match found
        """
        for pattern in patterns:
            matches = list(folder_path.glob(pattern))
            if matches:
                return matches[0]
        return None
