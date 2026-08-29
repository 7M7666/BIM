import json

import pytest

from bim_evidence_qa.domain import AggregateFunction, QueryOperation, QueryPlan
from bim_evidence_qa.evaluation import (
    EvaluationCase,
    EvaluationRunner,
    FailureCategory,
    load_evaluation_cases,
)
from bim_evidence_qa.evaluation.development_cases import DEVELOPMENT_CASES
from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner, LLMProviderError


class FixedPlanner:
    def __init__(self, plan: QueryPlan) -> None:
        self.plan_result = plan

    def plan(self, question, catalog):
        return self.plan_result


class FailedProviderPlanner:
    def plan(self, question, catalog):
        raise LLMProviderError("provider unavailable")


@pytest.fixture
def development_report(synthetic_dataset):
    return EvaluationRunner(DevelopmentNaturalLanguagePlanner()).run(
        synthetic_dataset,
        DEVELOPMENT_CASES,
    )


def test_evaluation_schema_rejects_supported_case_without_operation():
    with pytest.raises(ValueError, match="require an expected operation"):
        EvaluationCase(
            id="invalid",
            question="How many rooms?",
            expected_operation=None,
            expected_value=5,
            expected_entity_ids=(),
            expected_global_ids=(),
            category="count",
        )


def test_evaluation_schema_loads_valid_json(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "count-spaces",
                    "question": "How many spaces?",
                    "expected_operation": "count",
                    "expected_value": 5,
                    "expected_entity_ids": ["space-1"],
                    "expected_global_ids": ["GLOBAL-1"],
                    "category": "count",
                }
            ]
        ),
        encoding="utf-8",
    )

    cases = load_evaluation_cases(path)

    assert cases[0].expected_operation is QueryOperation.COUNT
    assert cases[0].expected_entity_ids == ("space-1",)


def test_planning_accuracy_is_calculated(development_report):
    metric = development_report.metrics.planning_accuracy

    assert (metric.correct, metric.total, metric.percentage) == (16, 16, 100.0)


def test_answer_accuracy_is_calculated(development_report):
    metric = development_report.metrics.answer_accuracy

    assert metric.correct == 15
    assert metric.total == 16
    assert metric.percentage == pytest.approx(93.75)


def test_evidence_accuracy_is_calculated(development_report):
    metric = development_report.metrics.evidence_accuracy

    assert (metric.correct, metric.total, metric.percentage) == (16, 16, 100.0)


def test_unsupported_rejection_accuracy_is_calculated(development_report):
    metric = development_report.metrics.unsupported_rejection_accuracy

    assert (metric.correct, metric.total, metric.percentage) == (4, 4, 100.0)


def test_deliberately_failing_case_is_classified(development_report):
    failure = next(
        result
        for result in development_report.failures
        if result.case.id == "deliberate-answer-failure"
    )

    assert failure.failure_category is FailureCategory.ANSWER_ERROR
    assert "Expected value 999" in failure.failure_reason


def test_wrong_operation_is_classified_as_planning_error(synthetic_dataset):
    case = EvaluationCase(
        "wrong-plan",
        "How many rooms?",
        QueryOperation.COUNT,
        5,
        (),
        (),
        "count",
    )
    report = EvaluationRunner(
        FixedPlanner(QueryPlan(operation=QueryOperation.FIND, kind="space"))
    ).run(synthetic_dataset, (case,))

    assert report.failures[0].failure_category is FailureCategory.PLANNING_ERROR


def test_wrong_global_id_is_classified_as_evidence_error(synthetic_dataset):
    case = EvaluationCase(
        "wrong-evidence",
        "Find Room 101",
        QueryOperation.FIND,
        None,
        ("space-101",),
        ("NOT-THE-GLOBAL-ID",),
        "find",
    )
    report = EvaluationRunner(
        FixedPlanner(QueryPlan(operation=QueryOperation.FIND, name="Room 101"))
    ).run(synthetic_dataset, (case,))

    assert report.failures[0].failure_category is FailureCategory.EVIDENCE_ERROR


def test_missing_attribute_is_classified_as_data_missing(synthetic_dataset):
    case = EvaluationCase(
        "missing-data",
        "Largest missing value",
        QueryOperation.AGGREGATE,
        None,
        (),
        (),
        "aggregate",
    )
    plan = QueryPlan(
        operation=QueryOperation.AGGREGATE,
        kind="space",
        aggregate_function=AggregateFunction.MAX,
        aggregate_field="missing_attribute",
    )
    report = EvaluationRunner(FixedPlanner(plan)).run(synthetic_dataset, (case,))

    assert report.failures[0].failure_category is FailureCategory.DATA_MISSING


def test_empty_aggregate_is_classified_as_execution_error(synthetic_dataset):
    case = EvaluationCase(
        "execution-failure",
        "Largest window value",
        QueryOperation.AGGREGATE,
        None,
        (),
        (),
        "aggregate",
    )
    plan = QueryPlan(
        operation=QueryOperation.AGGREGATE,
        kind="window",
        aggregate_function=AggregateFunction.MAX,
        aggregate_field="area",
    )
    report = EvaluationRunner(FixedPlanner(plan)).run(synthetic_dataset, (case,))

    assert report.failures[0].failure_category is FailureCategory.EXECUTION_ERROR


def test_provider_failure_is_saved_as_planning_error(synthetic_dataset):
    case = EvaluationCase(
        "provider-failure",
        "How many rooms?",
        QueryOperation.COUNT,
        5,
        (),
        (),
        "count",
    )

    report = EvaluationRunner(FailedProviderPlanner()).run(
        synthetic_dataset,
        (case,),
    )

    assert report.failures[0].failure_category is FailureCategory.PLANNING_ERROR
    assert report.failures[0].failure_reason == "provider unavailable"
