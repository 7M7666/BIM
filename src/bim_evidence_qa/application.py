from dataclasses import dataclass
import re

from bim_evidence_qa.answering import Answer, AnswerBuilder
from bim_evidence_qa.domain import (
    BuildingDataset,
    BuildingEntity,
    QueryOperation,
    QueryPlan,
    QueryResult,
    ResolutionError,
)
from bim_evidence_qa.query import QueryCatalog, QueryEngine, QueryPlanner
from bim_evidence_qa.query.properties import requested_property
from bim_evidence_qa.query.terminology import normalize_question


@dataclass(frozen=True, slots=True)
class ApplicationQueryResult:
    question: str
    plan: QueryPlan
    result: QueryResult
    answer: Answer


@dataclass(frozen=True, slots=True)
class ConversationContext:
    """The single, verified fact that may be carried into the next question."""

    operation: QueryOperation
    kind: str | None
    object_name: str | None = None

    @classmethod
    def from_outcome(cls, outcome: ApplicationQueryResult) -> "ConversationContext":
        entity = _single_explicit_entity(outcome)
        return cls(
            operation=outcome.plan.operation,
            kind=outcome.plan.kind,
            object_name=entity.name if entity else None,
        )


_SUPPORTED_KIND_TERMS = frozenset({
    "beam", "beams", "column", "columns", "slab", "slabs", "footing", "footings",
    "foundation", "foundations", "pile", "piles", "door", "doors", "window", "windows",
    "wall", "walls", "space", "spaces", "room", "rooms", "storey", "storeys",
    "level", "levels",
})
_PRONOUN_PATTERN = re.compile(
    r"\b(?:it|this|that)\b|它|这个|那个|该构件|这[扇根块个]|那[扇根块个]",
    re.IGNORECASE,
)
_COUNT_FOLLOW_UP_PATTERN = re.compile(
    r"只看|只统计|只算|仅看|only\b|just\b|数一下|统计一下",
    re.IGNORECASE,
)
_LOCATION_FOLLOW_UP_PATTERN = re.compile(
    r"\b(?:where|which\s+level|what\s+level)\b|在哪(?:一)?层|位于哪层|属于哪层",
    re.IGNORECASE,
)


def resolve_follow_up_question(question: str, context: ConversationContext | None) -> str:
    """Expand conservative one-turn follow-ups before invoking a query planner.

    This is deliberately limited to a previously identified single object and a
    count narrowed to a stated storey. It never selects one object from a list.
    """

    normalized = normalize_question(question)
    property_name = requested_property(normalized)
    has_pronoun = bool(_PRONOUN_PATTERN.search(question))
    if property_name is not None and has_pronoun:
        if context is None or context.object_name is None:
            raise ResolutionError(
                "needs_context",
                "This property follow-up needs one object identified in the previous answer.",
            )
        return f"What is the {property_name} of {context.object_name}?"

    if has_pronoun and _LOCATION_FOLLOW_UP_PATTERN.search(question):
        if context is None or context.object_name is None:
            raise ResolutionError(
                "needs_context",
                "This location follow-up needs one object identified in the previous answer.",
            )
        return f"Which level contains {context.object_name}?"

    level = _follow_up_level(question)
    if level is not None and _is_count_follow_up(question, context):
        if context is None or context.operation is not QueryOperation.COUNT or context.kind is None:
            raise ResolutionError(
                "needs_context",
                "This storey follow-up needs a previous count of one entity kind.",
            )
        return f"How many {context.kind}s are on {level}?"

    if _needs_count_context(normalized, question):
        raise ResolutionError(
            "needs_context",
            "Specify which supported entity kind to count.",
        )
    return question


def _single_explicit_entity(outcome: ApplicationQueryResult) -> BuildingEntity | None:
    if outcome.plan.operation is not QueryOperation.FIND:
        return None
    if len(outcome.result.entities) != 1:
        return None
    return outcome.result.entities[0]


def _follow_up_level(question: str) -> str | None:
    english = re.search(r"\b(?:level|storey)\s*(\d+)\b", question, re.IGNORECASE)
    if english:
        return f"Level {english.group(1)}"
    chinese = re.search(r"第?([一二三四五六七八九十\d]+)层", question)
    if chinese is None:
        return None
    numerals = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5"}
    value = numerals.get(chinese.group(1), chinese.group(1))
    return f"Level {value}" if value.isdigit() else None


def _is_count_follow_up(question: str, context: ConversationContext | None) -> bool:
    if _COUNT_FOLLOW_UP_PATTERN.search(question):
        return True
    compact = re.sub(r"[\s？?。.！!]", "", question)
    return context is not None and compact in {"二层呢", "第二层呢", "Level2"}


def _needs_count_context(normalized_question: str, raw_question: str) -> bool:
    tokens = set(re.findall(r"[a-z]+", normalized_question.casefold()))
    has_kind = bool(tokens & _SUPPORTED_KIND_TERMS)
    return not has_kind and bool(
        re.search(r"数(?:一)?下|统计(?:一)?下|\bcount\b|\bhow many\b", raw_question, re.IGNORECASE)
    )


def run_question(
    dataset: BuildingDataset,
    question: str,
    planner: QueryPlanner,
    context: ConversationContext | None = None,
) -> ApplicationQueryResult:
    catalog = QueryCatalog.from_dataset(dataset)
    plan = planner.plan(resolve_follow_up_question(question, context), catalog)
    result = QueryEngine().execute(plan, dataset)
    answer = AnswerBuilder().build(plan, result)
    return ApplicationQueryResult(
        question=question,
        plan=plan,
        result=result,
        answer=answer,
    )
