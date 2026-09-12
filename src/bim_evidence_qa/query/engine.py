from statistics import fmean
from dataclasses import replace

from bim_evidence_qa.query.catalog import REFERENCE_LEVEL_FIELD
from bim_evidence_qa.query.properties import DISPLAY_LIMIT, resolve_property

from bim_evidence_qa.domain import (
    AggregateFunction,
    BuildingDataset,
    BuildingEntity,
    FilterCondition,
    FilterOperator,
    LocationValue,
    QueryOperation,
    QueryPlan,
    QueryResult,
    ScalarValue,
    ResolutionError,
    PropertySource,
)


class QueryExecutionError(ValueError):
    """Raised when a valid query plan cannot be executed on a dataset."""


class UnknownFieldError(QueryExecutionError):
    """Raised when a query references a field missing from an entity."""


class IncompleteDataError(UnknownFieldError):
    """Raised when an aggregate field is missing from some candidate entities."""

    def __init__(
        self,
        *,
        field: str,
        target_kind: str,
        available_count: int,
        total_count: int,
        missing_entity_ids: tuple[str, ...],
    ) -> None:
        self.field = field
        self.target_kind = target_kind
        self.available_count = available_count
        self.total_count = total_count
        self.missing_entity_ids = missing_entity_ids
        missing = ", ".join(missing_entity_ids)
        super().__init__(
            f"Field '{field}' for target kind '{target_kind}' is available for "
            f"{available_count} of {total_count} entities. Missing entity IDs: "
            f"{missing}. The query cannot be answered reliably."
        )


class QueryEngine:
    _OVERVIEW_KINDS = (
        "storey", "space", "door", "window", "wall", "beam", "column", "slab",
        "footing", "pile",
    )
    _ENTITY_FIELDS = {
        "entity_id",
        "kind",
        "name",
        "global_id",
        "container_id",
    }

    def execute(self, plan: QueryPlan, dataset: BuildingDataset) -> QueryResult:
        if plan.operation is QueryOperation.OVERVIEW:
            counts = {
                kind: sum(entity.kind == kind for entity in dataset.entities)
                for kind in self._OVERVIEW_KINDS
            }
            return QueryResult(
                operation=plan.operation,
                entities=(),
                overview_counts={kind: count for kind, count in counts.items() if count > 0},
            )

        if plan.operation is QueryOperation.LOCATION:
            entities = self._select(plan, dataset)
            storeys_by_id = {
                entity.entity_id: entity.name
                for entity in dataset.entities
                if entity.kind == "storey" and entity.name is not None
            }
            locations = {}
            missing_entity_ids = []
            for entity in entities:
                if entity.container_id in storeys_by_id:
                    locations[entity.entity_id] = LocationValue(
                        "spatial_containment", storeys_by_id[entity.container_id]
                    )
                elif isinstance(
                    reference_level := entity.attributes.get(REFERENCE_LEVEL_FIELD), str
                ) and reference_level.strip():
                    locations[entity.entity_id] = LocationValue(
                        "reference_level", reference_level
                    )
                else:
                    missing_entity_ids.append(entity.entity_id)
            if missing_entity_ids:
                raise ResolutionError(
                    "missing_data",
                    "Level data is unavailable for: " + ", ".join(missing_entity_ids),
                )
            return QueryResult(
                operation=plan.operation,
                entities=entities,
                locations=locations,
            )

        entities = self._select(plan, dataset)
        diagnostics = self._level_diagnostics(plan, dataset)

        if plan.requested_property is not None:
            if len(entities) != 1:
                code = "entity_not_found" if not entities else "ambiguous"
                raise ResolutionError(code, "Property lookup requires exactly one matching object.",
                                      tuple(e.entity_id for e in entities))
            entity = entities[0]
            if plan.requested_property == "properties":
                properties = tuple(sorted(entity.properties, key=lambda p: (
                    p.source is not PropertySource.QUANTITY, p.path, p.source_id or 0
                )))
                if not properties:
                    raise ResolutionError("missing", "No scalar properties with IFC provenance are available.")
                if len(properties) > DISPLAY_LIMIT:
                    diagnostics += (f"Showing {DISPLAY_LIMIT} of {len(properties)} scalar properties; quantities first.",)
                properties = properties[:DISPLAY_LIMIT]
                value = None
            else:
                properties = (resolve_property(entity, plan.requested_property),)
                value = properties[0].value
            return QueryResult(plan.operation, entities, value, diagnostics, properties)

        if plan.operation in {QueryOperation.FIND, QueryOperation.FILTER}:
            return QueryResult(operation=plan.operation, entities=entities, diagnostics=diagnostics)
        if plan.operation is QueryOperation.COUNT:
            return QueryResult(
                operation=plan.operation,
                entities=entities,
                value=len(entities),
                diagnostics=diagnostics,
            )
        if plan.operation is QueryOperation.AGGREGATE:
            return replace(self._aggregate(plan, entities), diagnostics=diagnostics)

        raise QueryExecutionError(f"Unsupported query operation: {plan.operation}")

    @staticmethod
    def _level_diagnostics(plan: QueryPlan, dataset: BuildingDataset) -> tuple[str, ...]:
        diagnostics = []
        for condition in plan.filters:
            if condition.field == REFERENCE_LEVEL_FIELD:
                diagnostics.append(
                    f"Property-based level: {REFERENCE_LEVEL_FIELD} {condition.operator.value} "
                    f"'{condition.value}'. This is not IfcBuildingStorey containment."
                )
            elif condition.field == "container_id":
                storey = next((e for e in dataset.entities
                               if e.kind == "storey" and e.entity_id == condition.value), None)
                if storey is not None:
                    diagnostics.append(
                        f"Spatial containment: IfcBuildingStorey {condition.operator.value} '{storey.name}'."
                    )
        return tuple(diagnostics)

    def _select(
        self, plan: QueryPlan, dataset: BuildingDataset
    ) -> tuple[BuildingEntity, ...]:
        selected = dataset.entities
        if plan.kind is not None:
            selected = tuple(entity for entity in selected if entity.kind == plan.kind)
        if plan.name is not None:
            selected = tuple(entity for entity in selected if entity.name == plan.name)
        for condition in plan.filters:
            selected = tuple(
                entity
                for entity in selected
                if self._matches(entity, condition)
            )
        return selected

    def _matches(self, entity: BuildingEntity, condition: FilterCondition) -> bool:
        actual = self._field_value(entity, condition.field)
        expected = condition.value

        try:
            if condition.operator is FilterOperator.EQ:
                return actual == expected
            if condition.operator is FilterOperator.NE:
                return actual != expected
            if condition.operator is FilterOperator.GT:
                return actual > expected  # type: ignore[operator]
            if condition.operator is FilterOperator.GTE:
                return actual >= expected  # type: ignore[operator]
            if condition.operator is FilterOperator.LT:
                return actual < expected  # type: ignore[operator]
            if condition.operator is FilterOperator.LTE:
                return actual <= expected  # type: ignore[operator]
        except TypeError as error:
            raise QueryExecutionError(
                f"Cannot apply '{condition.operator.value}' to field "
                f"'{condition.field}' on entity '{entity.entity_id}'."
            ) from error

        raise QueryExecutionError(
            f"Unsupported filter operator: {condition.operator}"
        )

    def _aggregate(
        self, plan: QueryPlan, entities: tuple[BuildingEntity, ...]
    ) -> QueryResult:
        if not entities:
            raise QueryExecutionError("Cannot aggregate an empty result set.")

        assert plan.aggregate_field is not None
        assert plan.aggregate_function is not None

        raw_values: list[ScalarValue] = []
        missing_entity_ids = []
        for entity in entities:
            try:
                value = self._field_value(entity, plan.aggregate_field)
            except UnknownFieldError:
                missing_entity_ids.append(entity.entity_id)
                continue
            raw_values.append(value)

        if missing_entity_ids:
            raise IncompleteDataError(
                field=plan.aggregate_field,
                target_kind=plan.kind or "entity",
                available_count=len(raw_values),
                total_count=len(entities),
                missing_entity_ids=tuple(missing_entity_ids),
            )

        values: list[int | float] = []
        for entity, value in zip(entities, raw_values, strict=True):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise QueryExecutionError(
                    f"Field '{plan.aggregate_field}' on entity "
                    f"'{entity.entity_id}' is not numeric."
                )
            values.append(value)

        if plan.aggregate_function is AggregateFunction.AVERAGE:
            return QueryResult(
                operation=plan.operation,
                entities=entities,
                value=fmean(values),
            )

        aggregate_value = (
            min(values)
            if plan.aggregate_function is AggregateFunction.MIN
            else max(values)
        )
        matching_entities = tuple(
            entity
            for entity, value in zip(entities, values, strict=True)
            if value == aggregate_value
        )
        return QueryResult(
            operation=plan.operation,
            entities=matching_entities,
            value=aggregate_value,
        )

    def _field_value(self, entity: BuildingEntity, field: str) -> ScalarValue:
        if field in self._ENTITY_FIELDS:
            return getattr(entity, field)
        if field in entity.attributes:
            return entity.attributes[field]
        raise UnknownFieldError(
            f"Field '{field}' does not exist on entity '{entity.entity_id}'."
        )
