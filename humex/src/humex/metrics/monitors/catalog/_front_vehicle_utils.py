"""Shared lane-graph front vehicle search used by FrontVehicleId and FrontVehicleDistance."""

import math


def find_front_vehicle_on_lane_path(ego, frame, scenario, max_search_distance=200.0):
    """Find the nearest vehicle ahead of ego on the lane-graph path.

    Two paths:

    Fast path — when ``scenario.role_table`` is present (built during the
    Hume conversion-task Stage 2), the precomputed table provides the
    answer in O(1) and is more accurate (uses ground-truth future ego
    trajectory rather than greedy forward BFS).

    Slow path — Frenet projection over a forward-BFS lane corridor, plus
    a proximity-corridor fallback for vehicles whose lane assignment hasn't
    caught up to a cut-in. Routed through ``scenario.map`` which is the
    :class:`HMap` facade in Hume-loaded scenarios — lane queries go
    to LaneMap v2.

    Args:
        ego: Ego vehicle object
        frame: Current frame containing all vehicles
        scenario: Scenario with map and ego_id
        max_search_distance: Max centerline distance (m) to search

    Returns:
        tuple: (vehicle_id, vehicle_obj, s_gap) or (None, None, None)
            s_gap is the centerline distance between ego and the front vehicle
            (center-to-center, not bumper-to-bumper).
    """
    # ---- Fast path: precomputed role table ----
    # isinstance gate so MagicMock'd scenarios in test fixtures don't snap
    # to the fast path with auto-generated mock attributes.
    from humex.hmap.role_table import RoleTable
    role_table = getattr(scenario, "role_table", None)
    if isinstance(role_table, RoleTable):
        try:
            frame_index = scenario.timestamps.index(frame.timestamp)
        except (ValueError, AttributeError):
            frame_index = -1
        if frame_index >= 0:
            front = role_table.front(frame_index)
            if front is None:
                return None, None, None
            agent = frame.obj_list.get(front.agent_id)
            if agent is None:
                return None, None, None
            return front.agent_id, agent, front.s_gap

    # ---- Slow path ----
    ego_position = ego.sp.position.to_tuple()
    ava_map = scenario.map
    ego_heading = ego.sp.heading.yaw if ego.sp.heading else None
    if ego_heading is not None and abs(ego_heading) > 10.0:
        ego_heading = math.radians(ego_heading)

    ego_lane_id = ava_map.find_closest_lane(ego_position, heading=ego_heading)
    if ego_lane_id is None:
        return None, None, None

    lane_path = ava_map.get_reachable_lanes(ego_lane_id, max_search_distance)
    reachable_set = set(lane_path)

    # Adjacent-lane merge probe: include left/right neighbours that merge
    # into the forward path. Use the HMap query API (LaneMap v2
    # segment ids) — NOT legacy map_data.left_lanes/right_lanes which are
    # keyed by source-lane ids and would mismatch.
    for lid in list(reachable_set):
        for adj in (ava_map.left_lanes(lid) + ava_map.right_lanes(lid)):
            if adj in reachable_set:
                continue
            if set(ava_map.next_lanes(adj)) & reachable_set:
                reachable_set.add(adj)

    s_ego = ava_map.project_onto_lane_path(ego_position[:2], lane_path)
    if s_ego is None:
        return None, None, None

    best_id = None
    best_obj = None
    best_gap = float('inf')

    # Max lateral distance from ego's heading axis to count as "in front"
    # (roughly one lane width — filters out adjacent-lane vehicles)
    max_lateral = ego.width * 1.5 if hasattr(ego, 'width') and ego.width else 3.5

    # Proximity corridor for vehicles that fail lane-membership check:
    # must be within this longitudinal and lateral distance to be considered.
    proximity_max_longitudinal = 30.0  # meters ahead
    proximity_max_lateral = max_lateral  # same as lane-based lateral filter

    # Ego heading for lateral/longitudinal decomposition
    ego_yaw = ego.sp.heading.yaw
    if abs(ego_yaw) > 10.0:
        ego_yaw = math.radians(ego_yaw)
    fwd_dx = math.cos(ego_yaw)
    fwd_dy = math.sin(ego_yaw)
    lat_dx = -math.sin(ego_yaw)
    lat_dy = math.cos(ego_yaw)

    for obj_id, obj in frame.obj_list.items():
        if obj_id == scenario.ego_id:
            continue

        obj_position = obj.sp.position.to_tuple()
        obj_heading = obj.sp.heading.yaw if obj.sp.heading else None
        if obj_heading is not None and abs(obj_heading) > 10.0:
            obj_heading = math.radians(obj_heading)

        dx = obj_position[0] - ego_position[0]
        dy = obj_position[1] - ego_position[1]
        lateral_dist = abs(dx * lat_dx + dy * lat_dy)

        # Check lane membership: vehicle must be in ego's lane or a forward-reachable lane
        obj_lane_id = ava_map.find_closest_lane(obj_position, heading=obj_heading)
        in_reachable_lane = obj_lane_id in reachable_set

        if not in_reachable_lane:
            # Proximity corridor fallback: vehicle isn't in a reachable lane
            # but may be physically cutting into ego's path.
            longitudinal_dist = dx * fwd_dx + dy * fwd_dy
            if (longitudinal_dist <= 0
                    or longitudinal_dist > proximity_max_longitudinal
                    or lateral_dist > proximity_max_lateral):
                continue
        else:
            # Lane-based lateral filter
            if lateral_dist > max_lateral:
                continue

        # Project onto ego's lane path
        s_obj = ava_map.project_onto_lane_path(obj_position[:2], lane_path)
        if s_obj is None:
            continue

        gap = s_obj - s_ego
        if gap > 0 and gap < best_gap:
            best_gap = gap
            best_id = obj_id
            best_obj = obj

    if best_id is None:
        return None, None, None

    return best_id, best_obj, best_gap
