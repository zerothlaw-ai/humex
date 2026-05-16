"""Per-frame ego-relative agent role table.

Built once at scenario import time (Stage 2 of the conversion-task pipeline)
by :func:`role_table_builder.build_role_table`, persisted as the sidecar
``role.pb`` next to scenario.pb / map.pb / lane_map.pb. Loaded by the
``Scenario`` and consumed by monitors that have migrated.

v1 populates ``front`` and ``rear`` only. The other slots
(``left_lead``, ``left_follow``, ``right_lead``, ``right_follow``,
``cross_traffic``) are reserved on the proto and will be populated by v2 —
no schema bump needed.

Why precompute? Two reasons:
  1. Speed — monitors avoid per-frame BFS+Frenet over the lane graph.
  2. Accuracy — at frame K we use the ego's actual *future* trajectory as
     the forward corridor, instead of greedy BFS that picks up every
     reachable lane (including ones ego will never enter).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Fixed order of the 5 reference points on every agent's bbox. The role
# builder writes these positions in this order; the proto field names line
# up; monitors and the UI consume them by index when convenient.
POINT_NAMES = ("center", "front_left", "front_right", "rear_left", "rear_right")


@dataclass
class DistanceRange:
    closest: float = 0.0  # 0.0 if bboxes overlap
    farthest: float = 0.0


@dataclass
class AgentRole:
    agent_id: int
    distance: DistanceRange = field(default_factory=DistanceRange)
    s_gap: float = 0.0  # signed centerline arc-length gap from ego


@dataclass
class PointLaneAssignment:
    """Lane id for each of an agent's five reference points (centroid + 4
    bbox corners). 0 = unassigned (off-road or outside any drivable polygon)."""
    center: int = 0
    front_left: int = 0
    front_right: int = 0
    rear_left: int = 0
    rear_right: int = 0

    def as_list(self) -> List[int]:
        return [self.center, self.front_left, self.front_right,
                self.rear_left, self.rear_right]

    def __iter__(self):
        return iter(self.as_list())


@dataclass
class AgentLaneFrame:
    agent_id: int
    lanes: PointLaneAssignment = field(default_factory=PointLaneAssignment)


@dataclass
class AgentCorridor:
    """Disambiguated lane sequence for each of an agent's five reference
    points across the full trajectory. Each list is ordered_unique."""
    agent_id: int
    center_corridor: List[int] = field(default_factory=list)
    front_left_corridor: List[int] = field(default_factory=list)
    front_right_corridor: List[int] = field(default_factory=list)
    rear_left_corridor: List[int] = field(default_factory=list)
    rear_right_corridor: List[int] = field(default_factory=list)

    def all_lanes(self) -> List[int]:
        """Union of all five point-corridors, deduplicated, in encounter order."""
        seen: set = set()
        out: List[int] = []
        for seq in (
            self.center_corridor,
            self.front_left_corridor,
            self.front_right_corridor,
            self.rear_left_corridor,
            self.rear_right_corridor,
        ):
            for lid in seq:
                if lid not in seen:
                    seen.add(lid)
                    out.append(lid)
        return out


@dataclass
class FrameRoles:
    frame_index: int
    timestamp_ns: int = 0
    # v1 — populated by build_role_table v1.0. None when no candidate.
    front: Optional[AgentRole] = None
    rear: Optional[AgentRole] = None
    # v2 — reserved; always None on v1 builds.
    left_lead: Optional[AgentRole] = None
    left_follow: Optional[AgentRole] = None
    right_lead: Optional[AgentRole] = None
    right_follow: Optional[AgentRole] = None
    cross_traffic: Optional[AgentRole] = None
    # v2.1 — alongside roles. An agent in the immediate side lane whose
    # centerline projection longitudinally overlaps ego's bbox. Mutually
    # exclusive with the same-side lead / follow.
    left_alongside: Optional[AgentRole] = None
    right_alongside: Optional[AgentRole] = None
    # v2 — multi-point lane occupancy for non-ego agents at this frame.
    agent_lanes: List[AgentLaneFrame] = field(default_factory=list)


class RoleTable:
    def __init__(
        self,
        algorithm_version: str = "role-table-v2.0",
        ego_id: int = 0,
        frames: Optional[List[FrameRoles]] = None,
        agent_corridors: Optional[List[AgentCorridor]] = None,
    ) -> None:
        self.algorithm_version = algorithm_version
        self.ego_id = ego_id
        self.frames: List[FrameRoles] = frames or []
        self.agent_corridors: List[AgentCorridor] = agent_corridors or []
        # Build a lookup once so frame-level queries are O(1).
        self._corridor_by_agent: Dict[int, AgentCorridor] = {
            c.agent_id: c for c in self.agent_corridors
        }

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    # ---- query API used by monitors ----

    def front(self, frame_index: int) -> Optional[AgentRole]:
        if 0 <= frame_index < len(self.frames):
            return self.frames[frame_index].front
        return None

    def rear(self, frame_index: int) -> Optional[AgentRole]:
        if 0 <= frame_index < len(self.frames):
            return self.frames[frame_index].rear
        return None

    def get_frame(self, frame_index: int) -> Optional[FrameRoles]:
        if 0 <= frame_index < len(self.frames):
            return self.frames[frame_index]
        return None

    def lanes_for(
        self, agent_id: int, frame_index: int
    ) -> Optional[PointLaneAssignment]:
        """5-point lane assignment for ``agent_id`` at ``frame_index``, or
        None when the agent isn't present at that frame (or v1 table)."""
        fr = self.get_frame(frame_index)
        if fr is None:
            return None
        for alf in fr.agent_lanes:
            if alf.agent_id == agent_id:
                return alf.lanes
        return None

    def corridors_for(self, agent_id: int) -> Optional[AgentCorridor]:
        """Per-point corridors for ``agent_id``. None for agents not in
        the table or v1 tables that didn't populate corridors."""
        return self._corridor_by_agent.get(agent_id)

    # ---- proto serialization ----

    @classmethod
    def from_proto(cls, pb) -> "RoleTable":
        frames: List[FrameRoles] = []
        for pb_fr in pb.frames:
            fr = FrameRoles(
                frame_index=pb_fr.frame_index,
                timestamp_ns=pb_fr.timestamp_ns,
                front=_role_from_proto(pb_fr, "front"),
                rear=_role_from_proto(pb_fr, "rear"),
                left_lead=_role_from_proto(pb_fr, "left_lead"),
                left_follow=_role_from_proto(pb_fr, "left_follow"),
                right_lead=_role_from_proto(pb_fr, "right_lead"),
                right_follow=_role_from_proto(pb_fr, "right_follow"),
                cross_traffic=_role_from_proto(pb_fr, "cross_traffic"),
                left_alongside=_role_from_proto(pb_fr, "left_alongside"),
                right_alongside=_role_from_proto(pb_fr, "right_alongside"),
                agent_lanes=[
                    AgentLaneFrame(
                        agent_id=alf.agent_id,
                        lanes=PointLaneAssignment(
                            center=alf.lanes.center,
                            front_left=alf.lanes.front_left,
                            front_right=alf.lanes.front_right,
                            rear_left=alf.lanes.rear_left,
                            rear_right=alf.lanes.rear_right,
                        ),
                    )
                    for alf in pb_fr.agent_lanes
                ],
            )
            frames.append(fr)
        agent_corridors = [
            AgentCorridor(
                agent_id=ac.agent_id,
                center_corridor=list(ac.center_corridor),
                front_left_corridor=list(ac.front_left_corridor),
                front_right_corridor=list(ac.front_right_corridor),
                rear_left_corridor=list(ac.rear_left_corridor),
                rear_right_corridor=list(ac.rear_right_corridor),
            )
            for ac in pb.agent_corridors
        ]
        return cls(
            algorithm_version=pb.algorithm_version,
            ego_id=pb.ego_id,
            frames=frames,
            agent_corridors=agent_corridors,
        )

    def to_proto(self):
        from humex.proto import role_pb2

        pb = role_pb2.RoleTable(
            algorithm_version=self.algorithm_version,
            ego_id=self.ego_id,
            frame_count=len(self.frames),
        )
        for fr in self.frames:
            pb_fr = pb.frames.add()
            pb_fr.frame_index = fr.frame_index
            pb_fr.timestamp_ns = fr.timestamp_ns
            _role_to_proto(pb_fr, "front", fr.front)
            _role_to_proto(pb_fr, "rear", fr.rear)
            _role_to_proto(pb_fr, "left_lead", fr.left_lead)
            _role_to_proto(pb_fr, "left_follow", fr.left_follow)
            _role_to_proto(pb_fr, "right_lead", fr.right_lead)
            _role_to_proto(pb_fr, "right_follow", fr.right_follow)
            _role_to_proto(pb_fr, "cross_traffic", fr.cross_traffic)
            _role_to_proto(pb_fr, "left_alongside", fr.left_alongside)
            _role_to_proto(pb_fr, "right_alongside", fr.right_alongside)
            for alf in fr.agent_lanes:
                pb_alf = pb_fr.agent_lanes.add()
                pb_alf.agent_id = alf.agent_id
                pb_alf.lanes.center      = alf.lanes.center
                pb_alf.lanes.front_left  = alf.lanes.front_left
                pb_alf.lanes.front_right = alf.lanes.front_right
                pb_alf.lanes.rear_left   = alf.lanes.rear_left
                pb_alf.lanes.rear_right  = alf.lanes.rear_right
        for ac in self.agent_corridors:
            pb_ac = pb.agent_corridors.add()
            pb_ac.agent_id = ac.agent_id
            pb_ac.center_corridor.extend(ac.center_corridor)
            pb_ac.front_left_corridor.extend(ac.front_left_corridor)
            pb_ac.front_right_corridor.extend(ac.front_right_corridor)
            pb_ac.rear_left_corridor.extend(ac.rear_left_corridor)
            pb_ac.rear_right_corridor.extend(ac.rear_right_corridor)
        return pb


def _role_from_proto(pb_fr, field_name: str) -> Optional[AgentRole]:
    if not pb_fr.HasField(field_name):
        return None
    pb_role = getattr(pb_fr, field_name)
    return AgentRole(
        agent_id=pb_role.agent_id,
        distance=DistanceRange(
            closest=pb_role.distance.closest,
            farthest=pb_role.distance.farthest,
        ),
        s_gap=pb_role.s_gap,
    )


def _role_to_proto(pb_fr, field_name: str, role: Optional[AgentRole]) -> None:
    if role is None:
        return
    pb_role = getattr(pb_fr, field_name)
    pb_role.agent_id = role.agent_id
    pb_role.distance.closest = role.distance.closest
    pb_role.distance.farthest = role.distance.farthest
    pb_role.s_gap = role.s_gap
