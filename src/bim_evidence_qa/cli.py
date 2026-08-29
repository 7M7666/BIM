import argparse
from pathlib import Path
from typing import Sequence

from bim_evidence_qa.answering import Answer, AnswerBuilder
from bim_evidence_qa.domain import (
    AggregateFunction,
    FilterCondition,
    FilterOperator,
    QueryOperation,
    QueryPlan,
    QueryResult,
)
from bim_evidence_qa.parsers import SyntheticFixtureParser
from bim_evidence_qa.query import (
    DevelopmentNaturalLanguagePlanner,
    QueryCatalog,
    QueryEngine,
)


DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "synthetic_project.json"
)


def main(argv: Sequence[str] | None = None) -> None:
    argument_parser = argparse.ArgumentParser(
        description="Run structured smoke queries against synthetic development data."
    )
    argument_parser.add_argument(
        "fixture",
        nargs="?",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Path to a synthetic-development-only JSON fixture.",
    )
    argument_parser.add_argument(
        "--storey",
        default="storey-level-2",
        help="Storey entity_id used by the storey filter smoke query.",
    )
    argument_parser.add_argument(
        "--question",
        help="Plan and execute one development-only natural-language question.",
    )
    arguments = argument_parser.parse_args(argv)

    dataset = SyntheticFixtureParser().parse(arguments.fixture)
    engine = QueryEngine()

    print("SYNTHETIC DEVELOPMENT DATA")
    print("NOT FOR EVALUATION")
    print(f"file: {arguments.fixture}")
    print(f"entities loaded: {len(dataset.entities)}")

    if arguments.question is not None:
        catalog = QueryCatalog.from_dataset(dataset)
        plan = DevelopmentNaturalLanguagePlanner().plan(
            arguments.question, catalog
        )
        result = engine.execute(plan, dataset)
        answer = AnswerBuilder().build(plan, result)
        _print_question_result(arguments.question, plan, result, answer)
        return

    queries = (
        (
            "spaces count",
            QueryPlan(operation=QueryOperation.COUNT, kind="space"),
        ),
        (
            "largest space by area",
            QueryPlan(
                operation=QueryOperation.AGGREGATE,
                kind="space",
                aggregate_function=AggregateFunction.MAX,
                aggregate_field="area",
            ),
        ),
        (
            f"spaces on {arguments.storey}",
            QueryPlan(
                operation=QueryOperation.FILTER,
                kind="space",
                filters=(
                    FilterCondition(
                        field="container_id",
                        operator=FilterOperator.EQ,
                        value=arguments.storey,
                    ),
                ),
            ),
        ),
    )

    for label, plan in queries:
        _print_result(label, engine.execute(plan, dataset))


def _print_result(label: str, result: QueryResult) -> None:
    value = result.value if result.value is not None else len(result.entities)
    print()
    print(label)
    print(f"operation: {result.operation.value}")
    print(f"result value: {value}")
    for entity in result.entities:
        print(f"entity: {entity.name} | GlobalId: {entity.global_id}")


def _print_question_result(
    question: str, plan: QueryPlan, result: QueryResult, answer: Answer
) -> None:
    print()
    print("QUESTION")
    print(question)
    print()
    print("QUERY PLAN")
    print(f"operation: {plan.operation.value}")
    if plan.kind is not None:
        print(f"kind: {plan.kind}")
    if plan.name is not None:
        print(f"name: {plan.name}")
    if plan.aggregate_function is not None:
        print(f"function: {plan.aggregate_function.value}")
    if plan.aggregate_field is not None:
        print(f"field: {plan.aggregate_field}")
    print()
    print("RESULT")
    value = result.value if result.value is not None else len(result.entities)
    print(f"value: {value}")
    print()
    print("ANSWER")
    print(answer.text)
    print()
    print("EVIDENCE")
    if not answer.evidence:
        print("none")
    for evidence in answer.evidence:
        print(f"entity: {evidence.name}")
        print(f"kind: {evidence.kind}")
        print(f"GlobalId: {evidence.global_id}")
    if answer.warnings:
        print()
        print("WARNINGS")
        for warning in answer.warnings:
            print(warning)


if __name__ == "__main__":
    main()
