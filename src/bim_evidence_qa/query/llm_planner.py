import json
from json import JSONDecodeError
from typing import Protocol

from bim_evidence_qa.domain import (
    AggregateFunction,
    FilterCondition,
    FilterOperator,
    QueryOperation,
    QueryPlan,
    ScalarValue,
)
from bim_evidence_qa.query.catalog import QueryCatalog


class InvalidPlannerOutputError(ValueError):
    """Raised when an LLM response cannot be validated as a grounded QueryPlan."""


class LLMTextProvider(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return provider text without interpreting building facts."""

        ...


class LLMQueryPlanner:
    _ALLOWED_KEYS = {
        "operation",
        "kind",
        "name",
        "filters",
        "aggregate_function",
        "aggregate_field",
    }
    _CORE_FIELDS = {
        "entity_id",
        "kind",
        "name",
        "global_id",
        "container_id",
    }

    def __init__(self, provider: LLMTextProvider) -> None:
        self._provider = provider

    def plan(self, question: str, catalog: QueryCatalog) -> QueryPlan:
        response = self._provider.complete(
            self._system_prompt(),
            self._user_prompt(question, catalog),
        )
        return self._parse_response(response, catalog)

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Convert the question into one JSON QueryPlan object. "
            "Do not answer the question, invent building facts, or return GlobalIds. "
            "Use only kinds, attributes, names, containers, and operations in the catalog. "
            "Allowed keys are operation, kind, name, filters, aggregate_function, "
            "and aggregate_field. Each filter has field, operator, and value. "
            "Allowed filter operators are eq, ne, gt, gte, lt, and lte. "
            "Return JSON only."
        )

    @staticmethod
    def _user_prompt(question: str, catalog: QueryCatalog) -> str:
        catalog_payload = {
            "kinds": sorted(catalog.kinds),
            "attributes_by_kind": {
                kind: sorted(attributes)
                for kind, attributes in sorted(catalog.attributes_by_kind.items())
            },
            "entity_names": sorted(catalog.entity_names),
            "container_ids": sorted(catalog.container_ids),
            "container_names": sorted(catalog.container_names),
            "operations": sorted(operation.value for operation in catalog.operations),
        }
        return json.dumps(
            {"question": question, "catalog": catalog_payload},
            ensure_ascii=False,
        )

    def _parse_response(
        self, response: str, catalog: QueryCatalog
    ) -> QueryPlan:
        try:
            payload = json.loads(response)
        except JSONDecodeError as error:
            raise InvalidPlannerOutputError(
                f"Planner returned malformed JSON: {error.msg}."
            ) from error
        if not isinstance(payload, dict):
            raise InvalidPlannerOutputError(
                "Planner output must be one JSON object."
            )

        unknown_keys = payload.keys() - self._ALLOWED_KEYS
        if unknown_keys:
            fields = ", ".join(sorted(unknown_keys))
            raise InvalidPlannerOutputError(
                f"Planner output contains unsupported fields: {fields}."
            )

        operation = self._operation(payload.get("operation"), catalog)
        kind = self._optional_string(payload.get("kind"), "kind")
        name = self._optional_string(payload.get("name"), "name")

        if kind is not None and kind not in catalog.kinds:
            raise InvalidPlannerOutputError(
                f"Planner returned unavailable entity kind '{kind}'."
            )
        if name is not None and name not in catalog.entity_names:
            raise InvalidPlannerOutputError(
                f"Planner returned unavailable entity name '{name}'."
            )

        filters = self._filters(payload.get("filters", []), kind, catalog)
        aggregate_function = self._aggregate_function(
            payload.get("aggregate_function")
        )
        aggregate_field = self._optional_string(
            payload.get("aggregate_field"), "aggregate_field"
        )

        self._validate_operation_fields(
            operation,
            kind,
            name,
            filters,
            aggregate_function,
            aggregate_field,
            catalog,
        )
        try:
            return QueryPlan(
                operation=operation,
                kind=kind,
                name=name,
                filters=filters,
                aggregate_function=aggregate_function,
                aggregate_field=aggregate_field,
            )
        except ValueError as error:
            raise InvalidPlannerOutputError(str(error)) from error

    @staticmethod
    def _operation(value: object, catalog: QueryCatalog) -> QueryOperation:
        try:
            operation = QueryOperation(value)
        except (TypeError, ValueError) as error:
            raise InvalidPlannerOutputError(
                f"Planner returned unsupported operation '{value}'."
            ) from error
        if operation not in catalog.operations:
            raise InvalidPlannerOutputError(
                f"Operation '{operation.value}' is unavailable."
            )
        return operation

    def _filters(
        self,
        value: object,
        kind: str | None,
        catalog: QueryCatalog,
    ) -> tuple[FilterCondition, ...]:
        if not isinstance(value, list):
            raise InvalidPlannerOutputError("Planner filters must be a JSON array.")

        filters = []
        for index, raw_filter in enumerate(value):
            if not isinstance(raw_filter, dict):
                raise InvalidPlannerOutputError(
                    f"Planner filter at index {index} must be an object."
                )
            if set(raw_filter) != {"field", "operator", "value"}:
                raise InvalidPlannerOutputError(
                    f"Planner filter at index {index} has invalid fields."
                )

            field = self._required_string(raw_filter["field"], "filter field")
            try:
                operator = FilterOperator(raw_filter["operator"])
            except (TypeError, ValueError) as error:
                raise InvalidPlannerOutputError(
                    f"Planner filter at index {index} has an invalid operator."
                ) from error
            filter_value = raw_filter["value"]
            if not self._is_scalar(filter_value):
                raise InvalidPlannerOutputError(
                    f"Planner filter at index {index} has a non-scalar value."
                )
            self._validate_filter_field(field, filter_value, kind, catalog)
            filters.append(FilterCondition(field, operator, filter_value))
        return tuple(filters)

    def _validate_filter_field(
        self,
        field: str,
        value: ScalarValue,
        kind: str | None,
        catalog: QueryCatalog,
    ) -> None:
        if field not in self._CORE_FIELDS:
            if kind is None or not catalog.supports_attribute(kind, field):
                raise InvalidPlannerOutputError(
                    f"Attribute '{field}' is unavailable for entity kind '{kind}'."
                )
        if field == "container_id" and value not in catalog.container_ids:
            raise InvalidPlannerOutputError(
                f"Container '{value}' is unavailable in the current dataset."
            )

    @staticmethod
    def _aggregate_function(value: object) -> AggregateFunction | None:
        if value is None:
            return None
        try:
            return AggregateFunction(value)
        except (TypeError, ValueError) as error:
            raise InvalidPlannerOutputError(
                f"Planner returned unsupported aggregate function '{value}'."
            ) from error

    @staticmethod
    def _validate_operation_fields(
        operation: QueryOperation,
        kind: str | None,
        name: str | None,
        filters: tuple[FilterCondition, ...],
        aggregate_function: AggregateFunction | None,
        aggregate_field: str | None,
        catalog: QueryCatalog,
    ) -> None:
        if operation is QueryOperation.FIND and kind is None and name is None:
            raise InvalidPlannerOutputError(
                "Find queries require an available kind or entity name."
            )
        if operation is QueryOperation.COUNT and kind is None:
            raise InvalidPlannerOutputError("Count queries require an available kind.")
        if operation is QueryOperation.FILTER and (kind is None or not filters):
            raise InvalidPlannerOutputError(
                "Filter queries require a kind and at least one filter."
            )
        if operation is QueryOperation.AGGREGATE:
            if kind is None or aggregate_function is None or aggregate_field is None:
                raise InvalidPlannerOutputError(
                    "Aggregate queries require kind, aggregate_function, and "
                    "aggregate_field."
                )
            if not catalog.supports_attribute(kind, aggregate_field):
                raise InvalidPlannerOutputError(
                    f"Attribute '{aggregate_field}' is unavailable for entity kind "
                    f"'{kind}'."
                )
        elif aggregate_function is not None or aggregate_field is not None:
            raise InvalidPlannerOutputError(
                "Aggregate fields are only valid for aggregate queries."
            )

    @staticmethod
    def _optional_string(value: object, field: str) -> str | None:
        if value is None:
            return None
        return LLMQueryPlanner._required_string(value, field)

    @staticmethod
    def _required_string(value: object, field: str) -> str:
        if not isinstance(value, str) or not value:
            raise InvalidPlannerOutputError(
                f"Planner field '{field}' must be a non-empty string."
            )
        return value

    @staticmethod
    def _is_scalar(value: object) -> bool:
        return value is None or isinstance(value, (str, int, float, bool))
