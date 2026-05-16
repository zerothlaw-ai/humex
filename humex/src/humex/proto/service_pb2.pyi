import scenario_pb2 as _scenario_pb2
import map_pb2 as _map_pb2
import metric_result_pb2 as _metric_result_pb2
import signal_pb2 as _signal_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SimulationRequest(_message.Message):
    __slots__ = ("scenario", "map", "config")
    SCENARIO_FIELD_NUMBER: _ClassVar[int]
    MAP_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    scenario: _scenario_pb2.ScenarioData
    map: _map_pb2.MapData
    config: SimulationConfig
    def __init__(self, scenario: _Optional[_Union[_scenario_pb2.ScenarioData, _Mapping]] = ..., map: _Optional[_Union[_map_pb2.MapData, _Mapping]] = ..., config: _Optional[_Union[SimulationConfig, _Mapping]] = ...) -> None: ...

class SimulationResult(_message.Message):
    __slots__ = ("success", "message", "result_scenario", "frames")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RESULT_SCENARIO_FIELD_NUMBER: _ClassVar[int]
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    result_scenario: _scenario_pb2.ScenarioData
    frames: _containers.RepeatedCompositeFieldContainer[_scenario_pb2.Frame]
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., result_scenario: _Optional[_Union[_scenario_pb2.ScenarioData, _Mapping]] = ..., frames: _Optional[_Iterable[_Union[_scenario_pb2.Frame, _Mapping]]] = ...) -> None: ...

class SimulationConfig(_message.Message):
    __slots__ = ("max_simulation_time", "time_step", "options")
    class OptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    MAX_SIMULATION_TIME_FIELD_NUMBER: _ClassVar[int]
    TIME_STEP_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    max_simulation_time: float
    time_step: float
    options: _containers.ScalarMap[str, str]
    def __init__(self, max_simulation_time: _Optional[float] = ..., time_step: _Optional[float] = ..., options: _Optional[_Mapping[str, str]] = ...) -> None: ...

class MetricsRequest(_message.Message):
    __slots__ = ("scenario_data", "analyzer_config_name", "map_data", "signal_data")
    SCENARIO_DATA_FIELD_NUMBER: _ClassVar[int]
    ANALYZER_CONFIG_NAME_FIELD_NUMBER: _ClassVar[int]
    MAP_DATA_FIELD_NUMBER: _ClassVar[int]
    SIGNAL_DATA_FIELD_NUMBER: _ClassVar[int]
    scenario_data: _scenario_pb2.ScenarioData
    analyzer_config_name: str
    map_data: _map_pb2.MapData
    signal_data: _signal_pb2.SignalData
    def __init__(self, scenario_data: _Optional[_Union[_scenario_pb2.ScenarioData, _Mapping]] = ..., analyzer_config_name: _Optional[str] = ..., map_data: _Optional[_Union[_map_pb2.MapData, _Mapping]] = ..., signal_data: _Optional[_Union[_signal_pb2.SignalData, _Mapping]] = ...) -> None: ...

class MetricsResult(_message.Message):
    __slots__ = ("success", "message", "metric_result")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    METRIC_RESULT_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    metric_result: _metric_result_pb2.MetricResult
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., metric_result: _Optional[_Union[_metric_result_pb2.MetricResult, _Mapping]] = ...) -> None: ...

class ScenarioLoadRequest(_message.Message):
    __slots__ = ("scenario_id",)
    SCENARIO_ID_FIELD_NUMBER: _ClassVar[int]
    scenario_id: str
    def __init__(self, scenario_id: _Optional[str] = ...) -> None: ...

class MapLoadRequest(_message.Message):
    __slots__ = ("map_id",)
    MAP_ID_FIELD_NUMBER: _ClassVar[int]
    map_id: str
    def __init__(self, map_id: _Optional[str] = ...) -> None: ...
