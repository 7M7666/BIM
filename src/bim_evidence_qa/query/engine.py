from statistics import fmean

from bim_evidence_qa.domain import (
    AggregateFunction,
    BuildingDataset,
    BuildingEntity,
    FilterCondition,
    FilterOperator,
    QueryOperation,
    QueryPlan,
    QueryResult,
    ScalarValue,
)


class QueryExecutionError(ValueError):
    """Raised when a valid query plan cannot be executed on a dataset."""


class UnknownFieldError(QueryExecutionError):
    """Raised when a query references a field missing from an entity."""


class QueryEngine:
    _ENTITY_FIELDS = {
        "entity_id",
        "kind",
        "name",
        "global_id",
        "container_id",
    }

    def execute(self, plan: QueryPlan, dataset: BuildingDataset) -> QueryResult:
        entities = self._select(plan, dataset)

        if plan.operation in {QueryOperation.FIND, QueryOperation.FILTER}:
            return QueryResult(operation=plan.operation, entities=entities)
        if plan.operation is QueryOperation.COUNT:
            return QueryResult(
                operation=plan.operation,
                entities=entities,
                value=len(entities),
            )
        if plan.operation is QueryOperation.AGGREGATE:
            return self._aggregate(plan, entities)

        raise QueryExecutionError(f"Unsupported query operation: {plan.operation}")

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

        values: list[int | float] = []
        for entity in entities:
            value = self._field_value(entity, plan.aggregate_field)
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
