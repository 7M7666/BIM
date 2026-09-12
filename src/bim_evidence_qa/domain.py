from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, TypeAlias


ScalarValue: TypeAlias = str | int | float | bool | None


class UnsupportedQueryError(ValueError):
    """The requested query type is not implemented."""

    code = "unsupported"

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": str(self), "candidates": []}


class ResolutionError(UnsupportedQueryError):
    def __init__(self, code: str, message: str, candidates: tuple[str, ...] = ()):
        self.code = code
        self.candidates = candidates
        super().__init__(message)

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": str(self), "candidates": list(self.candidates)}


class PropertySource(str, Enum):
    ATTRIBUTE = "IFC Attribute"
    PSET = "Property Set"
    QUANTITY = "Quantity Set"
    RELATIONSHIP = "Relationship-derived value"


@dataclass(frozen=True, slots=True)
class PropertyValue:
    source: PropertySource
    set_name: str
    field_name: str
    value: ScalarValue
    measure_type: str | None = None
    unit: str | None = None
    source_id: int | None = None
    unit_source: str | None = None
    inherited: bool = False

    @property
    def path(self) -> str:
        return f"{self.set_name}.{self.field_name}"


@dataclass(frozen=True, slots=True)
class BuildingEntity:
    entity_id: str
    kind: str
    name: str | None = None
    global_id: str | None = None
    container_id: str | None = None
    attributes: Mapping[str, ScalarValue] = field(default_factory=dict)
    properties: tuple[PropertyValue, ...] = ()


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
    OVERVIEW = "overview"
    LOCATION = "location"


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
class LocationValue:
    source: str
    level: str


@dataclass(frozen=True, slots=True)
class QueryPlan:
    operation: QueryOperation
    kind: str | None = None
    name: str | None = None
    filters: tuple[FilterCondition, ...] = ()
    aggregate_function: AggregateFunction | None = None
    aggregate_field: str | None = None
    requested_property: str | None = None

    def __post_init__(self) -> None:
        if self.requested_property is not None and self.operation is not QueryOperation.FIND:
            raise ValueError("requested_property is only valid for find queries.")
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
        if self.operation is QueryOperation.OVERVIEW and (
            self.kind is not None or self.name is not None or self.filters
        ):
            raise ValueError("Overview queries cannot select a specific entity or scope.")


@dataclass(frozen=True, slots=True)
class QueryResult:
    operation: QueryOperation
    entities: tuple[BuildingEntity, ...]
    value: ScalarValue = None
    diagnostics: tuple[str, ...] = ()
    properties: tuple[PropertyValue, ...] = ()
    overview_counts: Mapping[str, int] = field(default_factory=dict)
    locations: Mapping[str, LocationValue] = field(default_factory=dict)
