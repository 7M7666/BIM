from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, TypeAlias


ScalarValue: TypeAlias = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class BuildingEntity:
    entity_id: str
    kind: str
    name: str | None = None
    global_id: str | None = None
    container_id: str | None = None
    attributes: Mapping[str, ScalarValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BuildingDataset:
    entities: tuple[BuildingEntity, ...]

    def __post_init__(self) -> None:
        entity_ids = [entity.entity_id for entity in self.entities]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("BuildingDataset contains duplicate entity_id values.")


class QueryOperation(str, Enum):
    FIND = "find"
    COUNT = "count"
    FILTER = "filter"
    AGGREGATE = "aggregate"


class FilterOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class AggregateFunction(str, Enum):
    MIN = "min"
    MAX = "max"
    AVERAGE = "average"


@dataclass(frozen=True, slots=True)
class FilterCondition:
    field: str
    operator: FilterOperator
    value: ScalarValue


@dataclass(frozen=True, slots=True)
class QueryPlan:
    operation: QueryOperation
    kind: str | None = None
    name: str | None = None
    filters: tuple[FilterCondition, ...] = ()
    aggregate_function: AggregateFunction | None = None
    aggregate_field: str | None = None

    def __post_init__(self) -> None:
        has_aggregate_fields = (
            self.aggregate_function is not None or self.aggregate_field is not None
        )
        if self.operation is QueryOperation.AGGREGATE:
            if self.aggregate_function is None or self.aggregate_field is None:
                raise ValueError(
                    "Aggregate queries require aggregate_function and aggregate_field."
                )
        elif has_aggregate_fields:
            raise ValueError(
                "aggregate_function and aggregate_field are only valid for aggregate queries."
            )


@dataclass(frozen=True, slots=True)
class QueryResult:
    operation: QueryOperation
    entities: tuple[BuildingEntity, ...]
    value: ScalarValue = None
    diagnostics: tuple[str, ...] = ()
