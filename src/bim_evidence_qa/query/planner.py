import re
from typing import Protocol

from bim_evidence_qa.domain import (
    AggregateFunction,
    QueryOperation,
    QueryPlan,
)
from bim_evidence_qa.query.catalog import QueryCatalog


class UnsupportedQueryError(ValueError):
    """Raised when a question cannot be grounded in the current query catalog."""


class QueryPlanner(Protocol):
    def plan(self, question: str, catalog: QueryCatalog) -> QueryPlan:
        """Convert a question into a structured plan without answering it."""

        ...


class DevelopmentNaturalLanguagePlanner:
    """Development-only keyword planner used to verify the planner boundary."""

    _ENTITY_ALIASES = {
        "room": "space",
        "rooms": "space",
        "space": "space",
        "spaces": "space",
        "door": "door",
        "doors": "door",
        "storey": "storey",
        "storeys": "storey",
        "level": "storey",
        "levels": "storey",
    }
    _ATTRIBUTE_ALIASES = {
        "area": "area",
        "width": "width",
        "color": "color",
        "colour": "color",
    }
    _COUNT_MARKERS = ("how many", "count", "number of")
    _MAX_MARKERS = ("largest", "biggest", "maximum", "max")
    _MIN_MARKERS = ("smallest", "minimum", "min")
    _AVERAGE_MARKERS = ("average", "mean")
    _FIND_MARKERS = ("find", "show", "locate")

    def plan(self, question: str, catalog: QueryCatalog) -> QueryPlan:
        normalized = " ".join(question.casefold().split())
        if not normalized:
            raise UnsupportedQueryError("Question cannot be empty.")

        tokens = set(re.findall(r"[a-z0-9_-]+", normalized))
        kind = self._resolve_kind(tokens, catalog)
        attribute = self._resolve_attribute(tokens, catalog)

        if self._contains_any(normalized, self._AVERAGE_MARKERS):
            return self._aggregate_plan(
                AggregateFunction.AVERAGE, kind, attribute, catalog
            )
        if self._contains_any(normalized, self._MAX_MARKERS):
            return self._aggregate_plan(
                AggregateFunction.MAX, kind, attribute, catalog
            )
        if self._contains_any(normalized, self._MIN_MARKERS):
            return self._aggregate_plan(
                AggregateFunction.MIN, kind, attribute, catalog
            )
        if self._contains_any(normalized, self._COUNT_MARKERS):
            self._require_operation(QueryOperation.COUNT, catalog)
            if kind is None:
                raise UnsupportedQueryError(
                    "No supported entity kind was found in the question."
                )
            return QueryPlan(operation=QueryOperation.COUNT, kind=kind)
        if self._contains_any(normalized, self._FIND_MARKERS):
            self._require_operation(QueryOperation.FIND, catalog)
            name = self._resolve_name(normalized, catalog)
            if name is None:
                raise UnsupportedQueryError(
                    "No entity name from the current dataset was found in the question."
                )
            return QueryPlan(operation=QueryOperation.FIND, name=name)

        raise UnsupportedQueryError(
            "The development planner does not understand this question."
        )

    def _resolve_kind(
        self, tokens: set[str], catalog: QueryCatalog
    ) -> str | None:
        for token in tokens:
            kind = self._ENTITY_ALIASES.get(token)
            if kind is not None:
                if kind not in catalog.kinds:
                    raise UnsupportedQueryError(
                        f"Entity kind '{kind}' is not available in the current dataset."
                    )
                return kind
        return None

    def _resolve_attribute(
        self, tokens: set[str], catalog: QueryCatalog
    ) -> str | None:
        for token in tokens:
            attribute = self._ATTRIBUTE_ALIASES.get(token)
            if attribute is not None:
                if attribute not in catalog.attributes:
                    raise UnsupportedQueryError(
                        f"Attribute '{attribute}' is not available in the current dataset."
                    )
                return attribute
        return None

    def _aggregate_plan(
        self,
        function: AggregateFunction,
        kind: str | None,
        attribute: str | None,
        catalog: QueryCatalog,
    ) -> QueryPlan:
        self._require_operation(QueryOperation.AGGREGATE, catalog)
        if kind is None:
            raise UnsupportedQueryError(
                "No supported entity kind was found in the question."
            )
        if attribute is None:
            raise UnsupportedQueryError(
                "No supported aggregate attribute was found in the question."
            )
        if not catalog.supports_attribute(kind, attribute):
            raise UnsupportedQueryError(
                f"Attribute '{attribute}' is not available for entity kind '{kind}'."
            )
        return QueryPlan(
            operation=QueryOperation.AGGREGATE,
            kind=kind,
            aggregate_function=function,
            aggregate_field=attribute,
        )

    @staticmethod
    def _resolve_name(question: str, catalog: QueryCatalog) -> str | None:
        for name in sorted(catalog.entity_names, key=len, reverse=True):
            if name.casefold() in question:
                return name
        return None

    @staticmethod
    def _contains_any(question: str, markers: tuple[str, ...]) -> bool:
        return any(marker in question for marker in markers)

    @staticmethod
    def _require_operation(
        operation: QueryOperation, catalog: QueryCatalog
    ) -> None:
        if operation not in catalog.operations:
            raise UnsupportedQueryError(
                f"Operation '{operation.value}' is not supported by the query engine."
            )
