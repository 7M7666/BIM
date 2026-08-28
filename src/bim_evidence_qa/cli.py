import argparse
from pathlib import Path
from typing import Sequence

from bim_evidence_qa.domain import (
    AggregateFunction,
    FilterCondition,
    FilterOperator,
    QueryOperation,
    QueryPlan,
    QueryResult,
)
from bim_evidence_qa.parsers import SyntheticFixtureParser
from bim_evidence_qa.query import QueryEngine


DEFAULT_FIXTURE = Path("tests/fixtures/synthetic_project.json")


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
    arguments = argument_parser.parse_args(argv)

    dataset = SyntheticFixtureParser().parse(arguments.fixture)
    engine = QueryEngine()

    print("SYNTHETIC DEVELOPMENT DATA")
    print("NOT FOR EVALUATION")
    print(f"file: {arguments.fixture}")
    print(f"entities loaded: {len(dataset.entities)}")

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


if __name__ == "__main__":
    main()
