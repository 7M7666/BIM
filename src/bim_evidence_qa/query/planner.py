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
from bim_evidence_qa.query.terminology import (
    is_location_intent,
    is_overview_intent,
    normalize_question,
)
from bim_evidence_qa.query.properties import requested_property, resolve_object


def split_level_scope(question: str) -> tuple[str, str | None, bool]:
    question = " ".join(question.split()).rstrip("?!")
    if (re.search(r"\b(?:contains?|belongs?|belong)\b", question, re.I)
            and not is_location_intent(question)):
        raise UnsupportedQueryError(
            "Relationship queries are unavailable; no relationship operation is supported."
        )
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
    """Terminology-driven development planner for existing query-engine operations."""

    _ENTITY_ALIASES = {
        "room": "space", "rooms": "space", "space": "space", "spaces": "space",
        "door": "door", "doors": "door", "window": "window", "windows": "window",
        "wall": "wall", "walls": "wall", "beam": "beam", "beams": "beam",
        "column": "column", "columns": "column", "slab": "slab", "slabs": "slab",
        "footing": "footing", "footings": "footing", "foundation": "footing",
        "foundations": "footing", "pile": "pile", "piles": "pile",
        "storey": "storey", "storeys": "storey", "level": "storey", "levels": "storey",
    }
    _ATTRIBUTE_ALIASES = {
        "area": "area", "width": "width", "length": "length", "height": "height",
        "volume": "volume", "color": "color", "colour": "color",
    }
    _COUNT_MARKERS = ("how many", "count", "number of")
    _MAX_MARKERS = ("largest", "biggest", "maximum", "max")
    _MIN_MARKERS = ("smallest", "minimum", "min")
    _AVERAGE_MARKERS = ("average", "mean")
    _FIND_MARKERS = ("find", "show", "locate", "list", "which", "what")
    _COMPARISON_OPERATORS = {
        ">=": FilterOperator.GTE, "<=": FilterOperator.LTE,
        ">": FilterOperator.GT, "<": FilterOperator.LT,
        "above": FilterOperator.GT, "below": FilterOperator.LT,
    }

    def plan(self, question: str, catalog: QueryCatalog) -> QueryPlan:
        question = normalize_question(question, (
            entity.name for entity in catalog.entities_by_id.values()
            if entity.name and entity.kind != "storey"
        ))
        if is_overview_intent(question) and self._resolve_name(question.casefold(), catalog) is None:
            self._require_operation(QueryOperation.OVERVIEW, catalog)
            return QueryPlan(operation=QueryOperation.OVERVIEW)
        if is_location_intent(question):
            return self._location_plan(question, catalog)

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
        if re.search(r"\b(?:intersect|intersection|geometr(?:y|ic))\b", normalized):
            raise UnsupportedQueryError("Geometry relationship queries are unavailable.")

        tokens = re.findall(r"[a-z0-9_-]+", normalized)
        property_request = requested_property(question, (p for p in catalog.attributes if "." in p))
        aggregate_markers = (*self._MAX_MARKERS, *self._MIN_MARKERS, *self._AVERAGE_MARKERS)
        if (property_request and not self._contains_any(normalized, aggregate_markers)
                and not self._has_comparison(normalized)):
            return self._property_plan(question, property_request, catalog)

        kind = self._resolve_kind(tokens, catalog)
        attribute = self._resolve_attribute(tokens, catalog)
        comparison = self._comparison_plan(normalized, kind, attribute, catalog)
        if comparison is not None:
            return comparison

        if self._contains_any(normalized, self._AVERAGE_MARKERS):
            return self._aggregate_plan(AggregateFunction.AVERAGE, kind, attribute, catalog)
        if self._contains_any(normalized, self._MAX_MARKERS):
            return self._aggregate_plan(AggregateFunction.MAX, kind, attribute, catalog)
        if self._contains_any(normalized, self._MIN_MARKERS):
            return self._aggregate_plan(AggregateFunction.MIN, kind, attribute, catalog)
        if self._contains_any(normalized, self._COUNT_MARKERS):
            self._require_operation(QueryOperation.COUNT, catalog)
            if kind is None:
                raise UnsupportedQueryError("No supported entity kind was found in the question.")
            return QueryPlan(operation=QueryOperation.COUNT, kind=kind)
        if self._contains_any(normalized, self._FIND_MARKERS):
            return self._find_plan(question, normalized, kind, catalog)

        raise UnsupportedQueryError("The development planner does not understand this question.")

    def _location_plan(self, question: str, catalog: QueryCatalog) -> QueryPlan:
        self._require_operation(QueryOperation.LOCATION, catalog)
        tokens = re.findall(r"[a-z0-9_-]+", question.casefold())
        kind = self._resolve_kind(tokens, catalog, ignore_storey=True)
        if kind is None:
            raise UnsupportedQueryError("No supported entity kind was found for the level query.")
        entity_id = self._explicit_entity_id(question, catalog, kind)
        filters = () if entity_id is None else (
            FilterCondition("entity_id", FilterOperator.EQ, entity_id),
        )
        return QueryPlan(operation=QueryOperation.LOCATION, kind=kind, filters=filters)

    def _comparison_plan(
        self, question: str, kind: str | None, attribute: str | None,
        catalog: QueryCatalog,
    ) -> QueryPlan | None:
        match = self._comparison_match(question)
        if match is None:
            return None
        self._require_operation(QueryOperation.FILTER, catalog)
        if kind is None or attribute is None:
            raise ResolutionError(
                "understood_but_unavailable",
                "A numeric filter requires a supported entity kind and property.",
            )
        if not catalog.supports_attribute(kind, attribute):
            raise ResolutionError(
                "understood_but_unavailable",
                f"Attribute '{attribute}' is not available for entity kind '{kind}'.",
            )
        value = float(match.group(2))
        if value.is_integer():
            value = int(value)
        return QueryPlan(
            operation=QueryOperation.FILTER,
            kind=kind,
            filters=(FilterCondition(attribute, self._COMPARISON_OPERATORS[match.group(1)], value),),
        )

    @staticmethod
    def _comparison_match(question: str) -> re.Match[str] | None:
        return re.search(
            r"(?:^|\s)(>=|<=|>|<|above|below)\s*(-?\d+(?:\.\d+)?)(?:\b|$)",
            question,
        )

    @classmethod
    def _has_comparison(cls, question: str) -> bool:
        return cls._comparison_match(question) is not None

    def _find_plan(
        self, question: str, normalized: str, kind: str | None, catalog: QueryCatalog,
    ) -> QueryPlan:
        self._require_operation(QueryOperation.FIND, catalog)
        name = self._resolve_name(normalized, catalog)
        if name is not None:
            matches = [entity for entity in catalog.entities_by_id.values() if entity.name == name]
            kinds = {entity.kind for entity in matches}
            if kind is not None and kind not in kinds:
                raise ResolutionError("entity_not_found", "Named object does not match the requested entity kind.")
            return QueryPlan(
                operation=QueryOperation.FIND,
                kind=kind or (next(iter(kinds)) if len(kinds) == 1 else None),
                name=name,
            )

        entity_id = self._explicit_entity_id(question, catalog, kind)
        if entity_id is not None:
            entity = catalog.entities_by_id[entity_id]
            return QueryPlan(
                operation=QueryOperation.FIND,
                kind=entity.kind,
                filters=(FilterCondition("entity_id", FilterOperator.EQ, entity_id),),
            )
        if kind is not None and self._is_collection_request(normalized):
            return QueryPlan(operation=QueryOperation.FIND, kind=kind)
        raw_identifier = re.fullmatch(r"(?:find|show|locate)\s+([A-Za-z0-9_$-]{4,})", normalized)
        if raw_identifier is not None:
            entity = resolve_object(raw_identifier.group(1), catalog.entities_by_id.values())
            return QueryPlan(
                operation=QueryOperation.FIND,
                kind=entity.kind,
                filters=(FilterCondition("entity_id", FilterOperator.EQ, entity.entity_id),),
            )
        if kind is None:
            raise UnsupportedQueryError("No supported entity kind was found in the question.")

        reference = re.sub(r"^(?:find|show|locate|list)\s+", "", question, flags=re.I)
        aliases = "|".join(self._ENTITY_ALIASES)
        reference = re.sub(
            r"^(?:(?:the|a|an)\s+)?(?:" + aliases + r")\s+", "", reference, flags=re.I,
        )
        entity = resolve_object(reference.strip(" ?!.\"'"), catalog.entities_by_id.values(), kind)
        return QueryPlan(
            operation=QueryOperation.FIND,
            kind=entity.kind,
            filters=(FilterCondition("entity_id", FilterOperator.EQ, entity.entity_id),),
        )

    @staticmethod
    def _is_collection_request(question: str) -> bool:
        return not re.search(r"\b(?:globalid|element\s*(?:number|id)?|id)\b|\b\d{5,}\b", question, re.I)

    @staticmethod
    def _explicit_entity_id(question: str, catalog: QueryCatalog, kind: str | None) -> str | None:
        match = re.search(r"\b(?:globalid|element\s*(?:number|id)?|id)\s*[:#]?\s*([A-Za-z0-9_$-]{4,})\b", question, re.I)
        if match:
            reference = match.group(1)
        else:
            long_number = re.search(r"(?<!\d)\d{5,}(?!\d)", question)
            reference = long_number.group(0) if long_number else None
        if reference is None:
            return None
        entity = resolve_object(reference, catalog.entities_by_id.values(), kind)
        return entity.entity_id

    def _property_plan(self, question: str, requested: str, catalog: QueryCatalog) -> QueryPlan:
        entities = tuple(catalog.entities_by_id.values())
        named = [entity for entity in entities if entity.name and re.search(
            r"(?<!\w)" + re.escape(entity.name) + r"(?!\w)", question, re.I
        )]
        if named:
            longest = max(len(entity.name) for entity in named)
            named = [entity for entity in named if len(entity.name) == longest]
            if len(named) != 1:
                raise ResolutionError("ambiguous", "Object name is ambiguous.", tuple(entity.entity_id for entity in named))
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
            entity_id = self._explicit_entity_id(remainder, catalog, kind)
            if entity_id is not None:
                entity = catalog.entities_by_id[entity_id]
            else:
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
        self, tokens: list[str], catalog: QueryCatalog, *, ignore_storey: bool = False,
    ) -> str | None:
        kinds = list(dict.fromkeys(
            self._ENTITY_ALIASES[token] for token in tokens
            if token in self._ENTITY_ALIASES and (not ignore_storey or self._ENTITY_ALIASES[token] != "storey")
        ))
        if len(kinds) > 1:
            raise ResolutionError("ambiguous", "Multiple supported entity kinds were requested.")
        if not kinds:
            return None
        kind = kinds[0]
        if kind not in catalog.kinds:
            if kind == "storey":
                raise ResolutionError(
                    "missing_storey_data",
                    "The IFC model has no IfcBuildingStorey entities, so its "
                    "storey count cannot be determined from spatial hierarchy.",
                )
            raise ResolutionError(
                "understood_but_unavailable",
                f"Entity kind '{kind}' is not available in the current dataset.",
            )
        return kind

    def _resolve_attribute(self, tokens: list[str], catalog: QueryCatalog) -> str | None:
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
        self, function: AggregateFunction, kind: str | None, attribute: str | None,
        catalog: QueryCatalog,
    ) -> QueryPlan:
        self._require_operation(QueryOperation.AGGREGATE, catalog)
        if kind is None:
            raise UnsupportedQueryError("No supported entity kind was found in the question.")
        if attribute is None or not catalog.supports_attribute(kind, attribute):
            detail = (
                f"Attribute '{attribute}' is not available for entity kind '{kind}'."
                if attribute is not None else
                f"No supported aggregate attribute is available for entity kind '{kind}'."
            )
            raise ResolutionError(
                "understood_but_unavailable",
                detail,
            )
        return QueryPlan(
            operation=QueryOperation.AGGREGATE, kind=kind,
            aggregate_function=function, aggregate_field=attribute,
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
    def _require_operation(operation: QueryOperation, catalog: QueryCatalog) -> None:
        if operation not in catalog.operations:
            raise UnsupportedQueryError(
                f"Operation '{operation.value}' is not supported by the query engine."
            )
