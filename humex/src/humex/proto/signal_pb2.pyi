from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SignalState(_message.Message):
    __slots__ = ("lane_id", "state")
    class State(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        LANE_STATE_UNKNOWN: _ClassVar[SignalState.State]
        LANE_STATE_ARROW_STOP: _ClassVar[SignalState.State]
        LANE_STATE_ARROW_CAUTION: _ClassVar[SignalState.State]
        LANE_STATE_ARROW_GO: _ClassVar[SignalState.State]
        LANE_STATE_STOP: _ClassVar[SignalState.State]
        LANE_STATE_CAUTION: _ClassVar[SignalState.State]
        LANE_STATE_GO: _ClassVar[SignalState.State]
        LANE_STATE_FLASHING_STOP: _ClassVar[SignalState.State]
        LANE_STATE_FLASHING_CAUTION: _ClassVar[SignalState.State]
    LANE_STATE_UNKNOWN: SignalState.State
    LANE_STATE_ARROW_STOP: SignalState.State
    LANE_STATE_ARROW_CAUTION: SignalState.State
    LANE_STATE_ARROW_GO: SignalState.State
    LANE_STATE_STOP: SignalState.State
    LANE_STATE_CAUTION: SignalState.State
    LANE_STATE_GO: SignalState.State
    LANE_STATE_FLASHING_STOP: SignalState.State
    LANE_STATE_FLASHING_CAUTION: SignalState.State
    LANE_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    lane_id: int
    state: SignalState.State
    def __init__(self, lane_id: _Optional[int] = ..., state: _Optional[_Union[SignalState.State, str]] = ...) -> None: ...

class SignalFrame(_message.Message):
    __slots__ = ("timestamp", "lane_signals")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    LANE_SIGNALS_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    lane_signals: _containers.RepeatedCompositeFieldContainer[SignalState]
    def __init__(self, timestamp: _Optional[int] = ..., lane_signals: _Optional[_Iterable[_Union[SignalState, _Mapping]]] = ...) -> None: ...

class SignalData(_message.Message):
    __slots__ = ("scenario_id", "frames")
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    frames: _containers.RepeatedCompositeFieldContainer[SignalFrame]
    def __init__(self, scenario_id: _Optional[str] = ..., frames: _Optional[_Iterable[_Union[SignalFrame, _Mapping]]] = ...) -> None: ...
