from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class NodeProto(_message.Message):
    __slots__ = ("id", "type", "name", "description", "inputs", "params", "tags")
    class ParamsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    INPUTS_FIELD_NUMBER: _ClassVar[int]
    PARAMS_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    id: int
    type: str
    name: str
    description: str
    inputs: _containers.RepeatedScalarFieldContainer[int]
    params: _containers.ScalarMap[str, str]
    tags: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, id: _Optional[int] = ..., type: _Optional[str] = ..., name: _Optional[str] = ..., description: _Optional[str] = ..., inputs: _Optional[_Iterable[int]] = ..., params: _Optional[_Mapping[str, str]] = ..., tags: _Optional[_Iterable[str]] = ...) -> None: ...

class MetricDAGMetadata(_message.Message):
    __slots__ = ("description", "source_file")
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FILE_FIELD_NUMBER: _ClassVar[int]
    description: str
    source_file: str
    def __init__(self, description: _Optional[str] = ..., source_file: _Optional[str] = ...) -> None: ...

class MetricDAGProto(_message.Message):
    __slots__ = ("nodes", "metadata")
    class NodesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: NodeProto
        def __init__(self, key: _Optional[int] = ..., value: _Optional[_Union[NodeProto, _Mapping]] = ...) -> None: ...
    NODES_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.MessageMap[int, NodeProto]
    metadata: MetricDAGMetadata
    def __init__(self, nodes: _Optional[_Mapping[int, NodeProto]] = ..., metadata: _Optional[_Union[MetricDAGMetadata, _Mapping]] = ...) -> None: ...
