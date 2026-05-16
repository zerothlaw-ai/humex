from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PointData(_message.Message):
    __slots__ = ("x", "y", "z")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ...) -> None: ...

class SegmentData(_message.Message):
    __slots__ = ("points",)
    POINTS_FIELD_NUMBER: _ClassVar[int]
    points: _containers.RepeatedCompositeFieldContainer[PointData]
    def __init__(self, points: _Optional[_Iterable[_Union[PointData, _Mapping]]] = ...) -> None: ...

class LaneData(_message.Message):
    __slots__ = ("id", "center_line", "left_boundary", "right_boundary", "speed_limit", "stop_point", "has_stop_sign")
    ID_FIELD_NUMBER: _ClassVar[int]
    CENTER_LINE_FIELD_NUMBER: _ClassVar[int]
    LEFT_BOUNDARY_FIELD_NUMBER: _ClassVar[int]
    RIGHT_BOUNDARY_FIELD_NUMBER: _ClassVar[int]
    SPEED_LIMIT_FIELD_NUMBER: _ClassVar[int]
    STOP_POINT_FIELD_NUMBER: _ClassVar[int]
    HAS_STOP_SIGN_FIELD_NUMBER: _ClassVar[int]
    id: int
    center_line: _containers.RepeatedCompositeFieldContainer[SegmentData]
    left_boundary: _containers.RepeatedCompositeFieldContainer[SegmentData]
    right_boundary: _containers.RepeatedCompositeFieldContainer[SegmentData]
    speed_limit: float
    stop_point: PointData
    has_stop_sign: bool
    def __init__(self, id: _Optional[int] = ..., center_line: _Optional[_Iterable[_Union[SegmentData, _Mapping]]] = ..., left_boundary: _Optional[_Iterable[_Union[SegmentData, _Mapping]]] = ..., right_boundary: _Optional[_Iterable[_Union[SegmentData, _Mapping]]] = ..., speed_limit: _Optional[float] = ..., stop_point: _Optional[_Union[PointData, _Mapping]] = ..., has_stop_sign: bool = ...) -> None: ...

class LaneConnections(_message.Message):
    __slots__ = ("lane_id", "connected_lane_ids")
    LANE_ID_FIELD_NUMBER: _ClassVar[int]
    CONNECTED_LANE_IDS_FIELD_NUMBER: _ClassVar[int]
    lane_id: int
    connected_lane_ids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, lane_id: _Optional[int] = ..., connected_lane_ids: _Optional[_Iterable[int]] = ...) -> None: ...

class MapData(_message.Message):
    __slots__ = ("lanes", "next_lanes", "prev_lanes", "left_lanes", "right_lanes", "map_name", "version", "created_at")
    class LanesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: LaneData
        def __init__(self, key: _Optional[int] = ..., value: _Optional[_Union[LaneData, _Mapping]] = ...) -> None: ...
    LANES_FIELD_NUMBER: _ClassVar[int]
    NEXT_LANES_FIELD_NUMBER: _ClassVar[int]
    PREV_LANES_FIELD_NUMBER: _ClassVar[int]
    LEFT_LANES_FIELD_NUMBER: _ClassVar[int]
    RIGHT_LANES_FIELD_NUMBER: _ClassVar[int]
    MAP_NAME_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    lanes: _containers.MessageMap[int, LaneData]
    next_lanes: _containers.RepeatedCompositeFieldContainer[LaneConnections]
    prev_lanes: _containers.RepeatedCompositeFieldContainer[LaneConnections]
    left_lanes: _containers.RepeatedCompositeFieldContainer[LaneConnections]
    right_lanes: _containers.RepeatedCompositeFieldContainer[LaneConnections]
    map_name: str
    version: float
    created_at: str
    def __init__(self, lanes: _Optional[_Mapping[int, LaneData]] = ..., next_lanes: _Optional[_Iterable[_Union[LaneConnections, _Mapping]]] = ..., prev_lanes: _Optional[_Iterable[_Union[LaneConnections, _Mapping]]] = ..., left_lanes: _Optional[_Iterable[_Union[LaneConnections, _Mapping]]] = ..., right_lanes: _Optional[_Iterable[_Union[LaneConnections, _Mapping]]] = ..., map_name: _Optional[str] = ..., version: _Optional[float] = ..., created_at: _Optional[str] = ...) -> None: ...

class RoadMap(_message.Message):
    __slots__ = ("name", "map_data")
    NAME_FIELD_NUMBER: _ClassVar[int]
    MAP_DATA_FIELD_NUMBER: _ClassVar[int]
    name: str
    map_data: MapData
    def __init__(self, name: _Optional[str] = ..., map_data: _Optional[_Union[MapData, _Mapping]] = ...) -> None: ...
