from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Statepoint(_message.Message):
    __slots__ = ("position", "velocity", "heading")
    class Position(_message.Message):
        __slots__ = ("x", "y", "z")
        X_FIELD_NUMBER: _ClassVar[int]
        Y_FIELD_NUMBER: _ClassVar[int]
        Z_FIELD_NUMBER: _ClassVar[int]
        x: float
        y: float
        z: float
        def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ...) -> None: ...
    class Velocity(_message.Message):
        __slots__ = ("x", "y", "z")
        X_FIELD_NUMBER: _ClassVar[int]
        Y_FIELD_NUMBER: _ClassVar[int]
        Z_FIELD_NUMBER: _ClassVar[int]
        x: float
        y: float
        z: float
        def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ...) -> None: ...
    class Heading(_message.Message):
        __slots__ = ("roll", "pitch", "yaw")
        ROLL_FIELD_NUMBER: _ClassVar[int]
        PITCH_FIELD_NUMBER: _ClassVar[int]
        YAW_FIELD_NUMBER: _ClassVar[int]
        roll: float
        pitch: float
        yaw: float
        def __init__(self, roll: _Optional[float] = ..., pitch: _Optional[float] = ..., yaw: _Optional[float] = ...) -> None: ...
    POSITION_FIELD_NUMBER: _ClassVar[int]
    VELOCITY_FIELD_NUMBER: _ClassVar[int]
    HEADING_FIELD_NUMBER: _ClassVar[int]
    position: Statepoint.Position
    velocity: Statepoint.Velocity
    heading: Statepoint.Heading
    def __init__(self, position: _Optional[_Union[Statepoint.Position, _Mapping]] = ..., velocity: _Optional[_Union[Statepoint.Velocity, _Mapping]] = ..., heading: _Optional[_Union[Statepoint.Heading, _Mapping]] = ...) -> None: ...

class Object(_message.Message):
    __slots__ = ("id", "length", "width", "height", "is_ego", "sp")
    ID_FIELD_NUMBER: _ClassVar[int]
    LENGTH_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    IS_EGO_FIELD_NUMBER: _ClassVar[int]
    SP_FIELD_NUMBER: _ClassVar[int]
    id: int
    length: float
    width: float
    height: float
    is_ego: bool
    sp: Statepoint
    def __init__(self, id: _Optional[int] = ..., length: _Optional[float] = ..., width: _Optional[float] = ..., height: _Optional[float] = ..., is_ego: bool = ..., sp: _Optional[_Union[Statepoint, _Mapping]] = ...) -> None: ...

class Frame(_message.Message):
    __slots__ = ("frame_id", "timestamp", "obj_list")
    class ObjListEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: Object
        def __init__(self, key: _Optional[int] = ..., value: _Optional[_Union[Object, _Mapping]] = ...) -> None: ...
    FRAME_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    OBJ_LIST_FIELD_NUMBER: _ClassVar[int]
    frame_id: int
    timestamp: int
    obj_list: _containers.MessageMap[int, Object]
    def __init__(self, frame_id: _Optional[int] = ..., timestamp: _Optional[int] = ..., obj_list: _Optional[_Mapping[int, Object]] = ...) -> None: ...

class ScenarioData(_message.Message):
    __slots__ = ("frequency", "duration", "map_name", "roster", "frames", "ego_id")
    class RosterEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: Object
        def __init__(self, key: _Optional[int] = ..., value: _Optional[_Union[Object, _Mapping]] = ...) -> None: ...
    class FramesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Frame
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Frame, _Mapping]] = ...) -> None: ...
    FREQUENCY_FIELD_NUMBER: _ClassVar[int]
    DURATION_FIELD_NUMBER: _ClassVar[int]
    MAP_NAME_FIELD_NUMBER: _ClassVar[int]
    ROSTER_FIELD_NUMBER: _ClassVar[int]
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    EGO_ID_FIELD_NUMBER: _ClassVar[int]
    frequency: float
    duration: float
    map_name: str
    roster: _containers.MessageMap[int, Object]
    frames: _containers.MessageMap[str, Frame]
    ego_id: int
    def __init__(self, frequency: _Optional[float] = ..., duration: _Optional[float] = ..., map_name: _Optional[str] = ..., roster: _Optional[_Mapping[int, Object]] = ..., frames: _Optional[_Mapping[str, Frame]] = ..., ego_id: _Optional[int] = ...) -> None: ...
