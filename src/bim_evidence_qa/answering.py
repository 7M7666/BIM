from dataclasses import dataclass

from bim_evidence_qa.domain import (
    AggregateFunction,
    QueryOperation,
    QueryPlan,
    QueryResult,
    ScalarValue,
    PropertyValue,
)


@dataclass(frozen=True, slots=True)
class EntityEvidence:
    entity_id: str
    kind: str
    name: str | None
    global_id: str | None
    properties: tuple[PropertyValue, ...] = ()


@dataclass(frozen=True, slots=True)
class Answer:
    status: str
    text: str
    value: ScalarValue
    evidence: tuple[EntityEvidence, ...]
    warnings: tuple[str, ...]


class AnswerBuilder:
    def build(self, plan: QueryPlan, result: QueryResult) -> Answer:
        if plan.operation is not result.operation:
            raise ValueError("QueryPlan and QueryResult operations do not match.")

        evidence = tuple(
            EntityEvidence(
                entity_id=entity.entity_id,
                kind=entity.kind,
                name=entity.name,
                global_id=entity.global_id,
                properties=result.properties if len(result.entities) == 1 else (),
            )
            for entity in result.entities
        )
        warnings = tuple(
            f"GlobalId unavailable for entity '{item.entity_id}'."
            for item in evidence
            if item.global_id is None
        )

        status, text = self._answer_text(plan, result)
        if result.diagnostics:
            text = " ".join((text, *result.diagnostics))
        return Answer(
            status=status,
            text=text,
            value=result.value,
            evidence=evidence,
            warnings=warnings,
        )

    def _answer_text(self, plan: QueryPlan, result: QueryResult) -> tuple[str, str]:
        if plan.requested_property is not None:
            entity = result.entities[0]
            if plan.requested_property == "properties":
                return "ok", f"Showing {len(result.properties)} scalar properties for {entity.name or entity.entity_id}."
            prop = result.properties[0]
            return "ok", (
                f"{entity.name or entity.entity_id}: {prop.path} = {prop.value} "
                f"{prop.unit or '(unit unavailable)'}."
            )
        if plan.operation is QueryOperation.COUNT:
            kind = plan.kind or "entity"
            return "ok", f"There are {result.value} {kind}s."

        if plan.operation is QueryOperation.FIND:
            if not result.entities:
                return "not_found", "No matching entities were found."
            if len(result.entities) == 1:
                name = result.entities[0].name or result.entities[0].entity_id
                return "ok", f"Found {name}."
            return "ok", f"Found {len(result.entities)} matching entities."

        if plan.operation is QueryOperation.FILTER:
            return "ok", f"Found {len(result.entities)} matching entities."

        if plan.operation is QueryOperation.AGGREGATE:
            assert plan.aggregate_function is not None
            assert plan.aggregate_field is not None
            kind = plan.kind or "entity"
            if plan.aggregate_function is AggregateFunction.AVERAGE:
                return (
                    "ok",
                    f"The average {kind} {plan.aggregate_field} is {result.value}.",
                )

            function = (
                "maximum"
                if plan.aggregate_function is AggregateFunction.MAX
                else "minimum"
            )
            if len(result.entities) == 1:
                entity = result.entities[0]
                name = entity.name or entity.entity_id
                return (
                    "ok",
                    f"{name} has the {function} {plan.aggregate_field}: "
                    f"{result.value}.",
                )
            return (
                "ok",
                f"The {function} {kind} {plan.aggregate_field} is {result.value}.",
            )

        raise ValueError(f"Unsupported query operation: {plan.operation}")
