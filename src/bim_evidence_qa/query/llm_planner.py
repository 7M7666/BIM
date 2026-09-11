import json
import re
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
from bim_evidence_qa.query.catalog import LevelResolutionError, QueryCatalog, REFERENCE_LEVEL_FIELD
from bim_evidence_qa.query.planner import (
    DevelopmentNaturalLanguagePlanner, UnsupportedQueryError,
    resolve_question_level, split_level_scope,
)
from bim_evidence_qa.query.terminology import normalize_question
from bim_evidence_qa.query.properties import SEMANTIC_FIELDS, requested_property, resolve_object


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
        "requested_property",
        "object_ref",
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
        normalized = normalize_question(question, (
            e.name for e in catalog.entities_by_id.values() if e.name and e.kind != "storey"
        ))
        subject, level, reference = split_level_scope(normalized)
        response = self._provider.complete(
            self._system_prompt(),
            self._user_prompt(question, catalog),
        )
        plan = self._parse_response(response, catalog)
        requested = requested_property(subject, (p for p in catalog.attributes if "." in p))
        aggregate_intent = DevelopmentNaturalLanguagePlanner._contains_any(
            subject.casefold(), (*DevelopmentNaturalLanguagePlanner._MAX_MARKERS,
                                 *DevelopmentNaturalLanguagePlanner._MIN_MARKERS,
                                 *DevelopmentNaturalLanguagePlanner._AVERAGE_MARKERS)
        )
        if plan.requested_property is not None:
            if requested != plan.requested_property:
                raise InvalidPlannerOutputError("Planner changed or invented the requested property.")
            local = DevelopmentNaturalLanguagePlanner()._property_plan(subject, requested, catalog)
            if plan.kind != local.kind or plan.filters[:1] != local.filters:
                raise InvalidPlannerOutputError("Planner changed the requested object.")
            if level is None and plan.filters != local.filters:
                raise InvalidPlannerOutputError("Planner added unrequested property filters.")
        elif requested and (not aggregate_intent or plan.operation is not QueryOperation.AGGREGATE):
            raise InvalidPlannerOutputError("Planner omitted the requested property.")
        if level is not None:
            subject_kind = DevelopmentNaturalLanguagePlanner()._resolve_kind(
                re.findall(r"[a-z0-9_-]+", subject.casefold()), catalog
            )
            if subject_kind is not None and plan.kind != subject_kind:
                raise InvalidPlannerOutputError("Planner changed the scoped query's entity kind.")
            expected = resolve_question_level(catalog, level, reference, plan.kind)
            level_filters = tuple(f for f in plan.filters if f.field in {"container_id", REFERENCE_LEVEL_FIELD})
            if level_filters != (expected,):
                raise InvalidPlannerOutputError("Planner omitted or changed the requested level scope.")
        return plan

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Convert the English or Chinese question into one JSON QueryPlan object. "
            "Do not answer the question, invent building facts, or return GlobalIds. "
            "Use only kinds, attributes, names, containers, and operations in the catalog. "
            "Every entity type, attribute, entity name, and container explicitly requested "
            "must have a direct semantic match in the catalog. Concepts absent from the "
            "catalog must be unsupported. Never substitute the nearest available concept: "
            "an absent elevator is not a door, absent stairs are not a storey, and an "
            "absent column is not a wall. An absent roof or furniture type is also "
            "unsupported. "
            "If the catalog cannot support the question, return exactly one JSON object "
            "with a non-empty unsupported string and no other keys. "
            "Allowed keys are operation, kind, name, filters, aggregate_function, "
            "aggregate_field, object_ref, and requested_property. Each filter has field, operator, and value. "
            "Allowed filter operators are eq, ne, gt, gte, lt, and lte. "
            "For spatial storey scope use field storey_name, operator eq, and the user's "
            "storey name; the application resolves the ID. Never emit container_id. "
            "For an explicitly requested Reference Level use field reference_level, "
            "operator eq, and its name. This is a property-based level, never spatial "
            "IfcBuildingStorey containment. Do not substitute it for on/in a storey. "
            "Relationship questions such as which storey contains an object are unsupported. "
            "For a single object property use operation find, canonical kind, object_ref "
            "(exact name, GlobalId or exported element ID), and requested_property. "
            "requested_property must be length, width, height, area, volume, properties, "
            "or an exact field path explicitly present in the user question. Never select "
            "a field path for a semantic property yourself; a local resolver decides. "
            "Never output values, units, or executable paths. "
            "Return JSON only."
        )

    @staticmethod
    def _user_prompt(question: str, catalog: QueryCatalog) -> str:
        return json.dumps(
            {
                "question": question,
                "catalog": catalog.as_prompt_payload(),
                "valid_query_plan_examples": LLMQueryPlanner._examples(catalog),
                "unsupported_example": {
                    "unsupported": "requested fact is unavailable in the catalog"
                },
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _examples(catalog: QueryCatalog) -> list[dict[str, object]]:
        examples: list[dict[str, object]] = []
        if catalog.kinds:
            examples.append(
                {
                    "operation": "count",
                    "kind": sorted(catalog.kinds)[0],
                }
            )
        if catalog.entity_names:
            examples.append(
                {
                    "operation": "find",
                    "name": sorted(catalog.entity_names)[0],
                }
            )
        return examples

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

        if set(payload) == {"unsupported"}:
            reason = self._required_string(payload["unsupported"], "unsupported")
            raise UnsupportedQueryError(f"LLM planner rejected question: {reason}")

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

        property_request = self._optional_string(payload.get("requested_property"), "requested_property")
        object_ref = self._optional_string(payload.get("object_ref"), "object_ref")
        if property_request is not None:
            if operation is not QueryOperation.FIND or kind is None or aggregate_field or aggregate_function:
                raise InvalidPlannerOutputError("Property queries require find and a canonical kind.")
            if property_request not in {*SEMANTIC_FIELDS, "properties"} and property_request not in catalog.attributes:
                raise InvalidPlannerOutputError("Property path is unavailable in the catalog.")
            if not (object_ref or name):
                raise InvalidPlannerOutputError("Property queries require an explicit object_ref.")
            entity = resolve_object(object_ref or name, catalog.entities_by_id.values(), kind)
            return QueryPlan(
                operation=operation, kind=kind,
                filters=(FilterCondition("entity_id", FilterOperator.EQ, entity.entity_id), *filters),
                requested_property=property_request,
            )
        if object_ref is not None:
            raise InvalidPlannerOutputError("object_ref requires requested_property.")

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
            if field == "container_id":
                raise InvalidPlannerOutputError("Use storey_name; internal container IDs must be resolved by the application.")
            if field in {"storey_name", "reference_level", REFERENCE_LEVEL_FIELD}:
                if operator is not FilterOperator.EQ or not isinstance(filter_value, str):
                    raise InvalidPlannerOutputError("Level filters require eq and a level name.")
                try:
                    condition = catalog.resolve_level(
                        filter_value, reference=field != "storey_name", kind=kind
                    )
                except LevelResolutionError as error:
                    raise InvalidPlannerOutputError(str(error)) from error
                filters.append(condition)
                continue
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
