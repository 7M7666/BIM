import re
from dataclasses import replace
from typing import Protocol

from bim_evidence_qa.domain import (
    AggregateFunction,
    FilterCondition,
    FilterOperator,
    QueryOperation,
    QueryPlan,
    ResolutionError,
    UnsupportedQueryError,
)
from bim_evidence_qa.query.catalog import LevelResolutionError, QueryCatalog
from bim_evidence_qa.query.terminology import normalize_question
from bim_evidence_qa.query.properties import requested_property, resolve_object


def split_level_scope(question: str) -> tuple[str, str | None, bool]:
    question = " ".join(question.split()).rstrip("?!")
    if re.search(r"\b(?:contains?|belongs?|belong)\b", question, re.I):
        raise UnsupportedQueryError("Relationship queries are unavailable; no relationship operation is supported.")
    reference = re.search(
        r"\b(?:have|has|with|having)\s+(?:a\s+)?reference\s+level\s*(?:=|:|is\b|of\b)?\s*(.+)$",
        question, re.I,
    )
    spatial = re.search(r"\b(?:on|in|at)\s+(.+)$", question, re.I)
    match = reference or spatial
    if match is None:
        return question, None, False
    name = match.group(1).strip().strip('"\'')
    if reference is None and name.casefold().rstrip(".") in {
        "this building", "the building", "this model", "the model",
    }:
        return question[:match.start()].strip(), None, False
    return question[:match.start()].strip(), name, reference is not None


def resolve_question_level(
    catalog: QueryCatalog, name: str, reference: bool, kind: str | None,
) -> FilterCondition:
    try:
        return catalog.resolve_level(name, reference=reference, kind=kind)
    except LevelResolutionError as error:
        # A sentence-ending period is optional; preserve periods in actual names first.
        if name.endswith(".") and "not found" in str(error):
            try:
                return catalog.resolve_level(name[:-1], reference=reference, kind=kind)
            except LevelResolutionError as retry_error:
                error = retry_error
        raise UnsupportedQueryError(str(error)) from error


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
        "window": "window",
        "windows": "window",
        "wall": "wall",
        "walls": "wall",
        "beam": "beam",
        "beams": "beam",
        "column": "column",
        "columns": "column",
        "slab": "slab",
        "slabs": "slab",
        "footing": "footing",
        "footings": "footing",
        "pile": "pile",
        "piles": "pile",
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
    _FIND_MARKERS = ("find", "show", "locate", "list")

    def plan(self, question: str, catalog: QueryCatalog) -> QueryPlan:
        question = normalize_question(question, (
            e.name for e in catalog.entities_by_id.values() if e.name and e.kind != "storey"
        ))
        subject, level, reference = split_level_scope(question)
        plan = self._plan_subject(subject, catalog)
        if level is not None:
            condition = resolve_question_level(catalog, level, reference, plan.kind)
            plan = replace(plan, filters=(*plan.filters, condition))
        return plan

    def _plan_subject(self, question: str, catalog: QueryCatalog) -> QueryPlan:
        normalized = " ".join(question.casefold().split())
        if not normalized:
            raise UnsupportedQueryError("Question cannot be empty.")

        tokens = re.findall(r"[a-z0-9_-]+", normalized)
        property_request = requested_property(question, (p for p in catalog.attributes if "." in p))
        aggregate_markers = (*self._MAX_MARKERS, *self._MIN_MARKERS, *self._AVERAGE_MARKERS)
        if property_request and not self._contains_any(normalized, aggregate_markers):
            return self._property_plan(question, property_request, catalog)
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
                if kind is not None and re.fullmatch(
                    r"(?:list|find|show)\s+(?:(?:all|the)\s+)?[a-z]+[.!?]?", normalized
                ):
                    return QueryPlan(operation=QueryOperation.FIND, kind=kind)
                reference = re.sub(r"^(?:find|show|locate|list)\s+", "", question, flags=re.I)
                aliases = "|".join(self._ENTITY_ALIASES)
                reference = re.sub(r"^(?:(?:the|a|an)\s+)?(?:" + aliases + r")\s+", "", reference, flags=re.I)
                entity = resolve_object(reference.strip(" ?!.\"'"), catalog.entities_by_id.values(), kind)
                return QueryPlan(operation=QueryOperation.FIND, kind=entity.kind,
                                 filters=(FilterCondition("entity_id", FilterOperator.EQ, entity.entity_id),))
            matches = [e for e in catalog.entities_by_id.values() if e.name == name]
            kinds = {e.kind for e in matches}
            if kind is not None and kind not in kinds:
                raise ResolutionError("entity_not_found", "Named object does not match the requested entity kind.")
            return QueryPlan(operation=QueryOperation.FIND, kind=kind or (next(iter(kinds)) if len(kinds) == 1 else None), name=name)

        raise UnsupportedQueryError(
            "The development planner does not understand this question."
        )

    def _property_plan(self, question: str, requested: str, catalog: QueryCatalog) -> QueryPlan:
        entities = tuple(catalog.entities_by_id.values())
        named = [e for e in entities if e.name and re.search(
            r"(?<!\w)" + re.escape(e.name) + r"(?!\w)", question, re.I
        )]
        if named:
            longest = max(len(e.name) for e in named)
            named = [e for e in named if len(e.name) == longest]
            if len(named) != 1:
                raise ResolutionError("ambiguous", "Object name is ambiguous.", tuple(e.entity_id for e in named))
            entity = named[0]
            subject = re.sub(re.escape(entity.name), " ", question, flags=re.I).replace(requested, " ")
            explicit_kind = self._resolve_kind(re.findall(r"[a-z0-9_-]+", subject.casefold()), catalog)
            if explicit_kind is not None and explicit_kind != entity.kind:
                raise ResolutionError("entity_not_found", "Named object does not match the requested entity kind.")
        else:
            if re.search(r"\b(?:this|it|these|unresolved_this)\b", question, re.I):
                raise ResolutionError("unsupported", "Object reference requires an explicit name or ID; pronouns are unsupported.")
            remainder = re.sub(re.escape(requested), " ", question, flags=re.I)
            kind = self._resolve_kind(re.findall(r"[a-z0-9_-]+", remainder.casefold()), catalog)
            stopwords = r"\b(?:what|is|the|of|show|me|list|all|has|have|how|long|wide|high|count|a|an|property|properties)\b"
            remainder = re.sub(stopwords, " ", remainder, flags=re.I)
            aliases = "|".join(self._ENTITY_ALIASES)
            remainder = re.sub(r"\b(?:" + aliases + r")\b", " ", remainder, flags=re.I)
            reference = " ".join(remainder.strip(" ?!.[]\"'").split())
            if not reference:
                raise ResolutionError("entity_not_found", "Specify an object name, GlobalId or exported element ID.")
            entity = resolve_object(reference, entities, kind)
        return QueryPlan(
            operation=QueryOperation.FIND, kind=entity.kind,
            filters=(FilterCondition("entity_id", FilterOperator.EQ, entity.entity_id),),
            requested_property=requested,
        )

    def _resolve_kind(
        self, tokens: list[str], catalog: QueryCatalog
    ) -> str | None:
        kinds = list(dict.fromkeys(
            self._ENTITY_ALIASES[token] for token in tokens if token in self._ENTITY_ALIASES
        ))
        if len(kinds) > 1:
            raise UnsupportedQueryError("Ambiguous query subject: multiple entity kinds.")
        if not kinds:
            return None
        kind = kinds[0]
        if kind not in catalog.kinds:
            raise UnsupportedQueryError(
                f"Entity kind '{kind}' is not available in the current dataset."
            )
        return kind

    def _resolve_attribute(
        self, tokens: list[str], catalog: QueryCatalog
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
        for name in sorted(catalog.entity_names, key=lambda value: (-len(value), value)):
            if re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", question):
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
