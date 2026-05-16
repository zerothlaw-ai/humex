from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MetricLeafFrameResult(_message.Message):
    __slots__ = ("timestamp", "numeric_value", "boolean_value", "string_value", "frame_result")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    NUMERIC_VALUE_FIELD_NUMBER: _ClassVar[int]
    BOOLEAN_VALUE_FIELD_NUMBER: _ClassVar[int]
    STRING_VALUE_FIELD_NUMBER: _ClassVar[int]
    FRAME_RESULT_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    numeric_value: float
    boolean_value: bool
    string_value: str
    frame_result: bool
    def __init__(self, timestamp: _Optional[int] = ..., numeric_value: _Optional[float] = ..., boolean_value: bool = ..., string_value: _Optional[str] = ..., frame_result: bool = ...) -> None: ...

class MetricLeafNodeResult(_message.Message):
    __slots__ = ("node_id", "name", "frame_results", "numeric_reduced", "boolean_reduced", "string_reduced", "reduced_result", "source_monitor_ids")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    FRAME_RESULTS_FIELD_NUMBER: _ClassVar[int]
    NUMERIC_REDUCED_FIELD_NUMBER: _ClassVar[int]
    BOOLEAN_REDUCED_FIELD_NUMBER: _ClassVar[int]
    STRING_REDUCED_FIELD_NUMBER: _ClassVar[int]
    REDUCED_RESULT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_MONITOR_IDS_FIELD_NUMBER: _ClassVar[int]
    node_id: int
    name: str
    frame_results: _containers.RepeatedCompositeFieldContainer[MetricLeafFrameResult]
    numeric_reduced: float
    boolean_reduced: bool
    string_reduced: str
    reduced_result: bool
    source_monitor_ids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, node_id: _Optional[int] = ..., name: _Optional[str] = ..., frame_results: _Optional[_Iterable[_Union[MetricLeafFrameResult, _Mapping]]] = ..., numeric_reduced: _Optional[float] = ..., boolean_reduced: bool = ..., string_reduced: _Optional[str] = ..., reduced_result: bool = ..., source_monitor_ids: _Optional[_Iterable[int]] = ...) -> None: ...

class MetricResult(_message.Message):
    __slots__ = ("evaluation_timestamp", "dag_description", "leaf_node_results", "final_result", "evaluation_time_seconds", "nodes_evaluated", "total_nodes")
    EVALUATION_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    DAG_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LEAF_NODE_RESULTS_FIELD_NUMBER: _ClassVar[int]
    FINAL_RESULT_FIELD_NUMBER: _ClassVar[int]
    EVALUATION_TIME_SECONDS_FIELD_NUMBER: _ClassVar[int]
    NODES_EVALUATED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_NODES_FIELD_NUMBER: _ClassVar[int]
    evaluation_timestamp: int
    dag_description: str
    leaf_node_results: _containers.RepeatedCompositeFieldContainer[MetricLeafNodeResult]
    final_result: bool
    evaluation_time_seconds: float
    nodes_evaluated: int
    total_nodes: int
    def __init__(self, evaluation_timestamp: _Optional[int] = ..., dag_description: _Optional[str] = ..., leaf_node_results: _Optional[_Iterable[_Union[MetricLeafNodeResult, _Mapping]]] = ..., final_result: bool = ..., evaluation_time_seconds: _Optional[float] = ..., nodes_evaluated: _Optional[int] = ..., total_nodes: _Optional[int] = ...) -> None: ...
