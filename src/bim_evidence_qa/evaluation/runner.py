from dataclasses import dataclass

from bim_evidence_qa.answering import AnswerBuilder
from bim_evidence_qa.domain import BuildingDataset
from bim_evidence_qa.evaluation.metrics import EvaluationMetrics, calculate_metrics
from bim_evidence_qa.evaluation.schema import (
    EvaluationCase,
    EvaluationCaseResult,
    FailureCategory,
)
from bim_evidence_qa.query import (
    InvalidPlannerOutputError,
    LLMProviderError,
    QueryCatalog,
    QueryEngine,
    QueryExecutionError,
    QueryPlanner,
    UnknownFieldError,
    UnsupportedQueryError,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    results: tuple[EvaluationCaseResult, ...]

    @property
    def metrics(self) -> EvaluationMetrics:
        return calculate_metrics(self.results)

    @property
    def failures(self) -> tuple[EvaluationCaseResult, ...]:
        return tuple(
            result for result in self.results if result.failure_category is not None
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "label": "DEVELOPMENT EVALUATION ONLY - NOT COURSE RESULTS",
            "metrics": self.metrics.as_dict(),
            "failures": [
                {
                    "id": result.case.id,
                    "question": result.case.question,
                    "case_category": result.case.category,
                    "failure_category": result.failure_category.value,
                    "reason": result.failure_reason,
                }
                for result in self.failures
                if result.failure_category is not None
            ],
        }


class EvaluationRunner:
    def __init__(self, planner: QueryPlanner) -> None:
        self._planner = planner

    def run(
        self,
        dataset: BuildingDataset,
        cases: tuple[EvaluationCase, ...],
    ) -> EvaluationReport:
        catalog = QueryCatalog.from_dataset(dataset)
        return EvaluationReport(
            results=tuple(self._run_case(dataset, catalog, case) for case in cases)
        )

    def _run_case(
        self,
        dataset: BuildingDataset,
        catalog: QueryCatalog,
        case: EvaluationCase,
    ) -> EvaluationCaseResult:
        try:
            plan = self._planner.plan(case.question, catalog)
        except UnsupportedQueryError as error:
            if case.expect_unsupported:
                return EvaluationCaseResult(
                    case=case,
                    unsupported_rejected=True,
                )
            return self._failure(
                case,
                FailureCategory.UNSUPPORTED_QUERY,
                str(error),
                planning_correct=False,
            )
        except InvalidPlannerOutputError as error:
            if case.expect_unsupported:
                return EvaluationCaseResult(
                    case=case,
                    unsupported_rejected=True,
                )
            return self._failure(
                case,
                FailureCategory.PLANNING_ERROR,
                str(error),
                planning_correct=False,
            )
        except LLMProviderError as error:
            return self._failure(
                case,
                FailureCategory.PLANNING_ERROR,
                str(error),
                planning_correct=False,
            )

        if case.expect_unsupported:
            return self._failure(
                case,
                FailureCategory.UNSUPPORTED_QUERY,
                "Unsupported question produced a QueryPlan.",
                plan=plan,
                unsupported_rejected=False,
            )

        planning_correct = plan.operation is case.expected_operation
        try:
            query_result = QueryEngine().execute(plan, dataset)
        except UnknownFieldError as error:
            return self._failure(
                case,
                FailureCategory.DATA_MISSING,
                str(error),
                plan=plan,
                planning_correct=planning_correct,
                answer_correct=False,
            )
        except QueryExecutionError as error:
            return self._failure(
                case,
                FailureCategory.EXECUTION_ERROR,
                str(error),
                plan=plan,
                planning_correct=planning_correct,
                answer_correct=False,
            )

        try:
            answer = AnswerBuilder().build(plan, query_result)
        except ValueError as error:
            return self._failure(
                case,
                FailureCategory.ANSWER_ERROR,
                str(error),
                plan=plan,
                planning_correct=planning_correct,
                answer_correct=False,
            )

        actual_entity_ids = tuple(entity.entity_id for entity in query_result.entities)
        actual_global_ids = tuple(item.global_id for item in answer.evidence)
        answer_correct = query_result.value == case.expected_value
        if case.expected_entity_ids:
            answer_correct = answer_correct and (
                set(actual_entity_ids) == set(case.expected_entity_ids)
            )

        evidence_correct = self._evidence_correct(
            case,
            actual_entity_ids,
            actual_global_ids,
        )
        failure_category = None
        failure_reason = None
        if not planning_correct:
            failure_category = FailureCategory.PLANNING_ERROR
            failure_reason = (
                f"Expected operation {case.expected_operation.value}; "
                f"received {plan.operation.value}."
            )
        elif not answer_correct:
            failure_category = FailureCategory.ANSWER_ERROR
            failure_reason = (
                f"Expected value {case.expected_value!r} and entity ids "
                f"{case.expected_entity_ids!r}; received value "
                f"{query_result.value!r} and entity ids {actual_entity_ids!r}."
            )
        elif evidence_correct is False:
            failure_category = FailureCategory.EVIDENCE_ERROR
            failure_reason = (
                f"Expected evidence GlobalIds {case.expected_global_ids!r}; "
                f"received {actual_global_ids!r}."
            )

        return EvaluationCaseResult(
            case=case,
            plan=plan,
            actual_value=query_result.value,
            actual_entity_ids=actual_entity_ids,
            actual_global_ids=actual_global_ids,
            planning_correct=planning_correct,
            answer_correct=answer_correct,
            evidence_correct=evidence_correct,
            failure_category=failure_category,
            failure_reason=failure_reason,
        )

    @staticmethod
    def _evidence_correct(
        case: EvaluationCase,
        actual_entity_ids: tuple[str, ...],
        actual_global_ids: tuple[str | None, ...],
    ) -> bool | None:
        if case.expected_global_ids:
            return set(actual_global_ids) == set(case.expected_global_ids)
        if case.expected_entity_ids:
            return set(actual_entity_ids) == set(case.expected_entity_ids)
        return None

    @staticmethod
    def _failure(
        case: EvaluationCase,
        category: FailureCategory,
        reason: str,
        **values: object,
    ) -> EvaluationCaseResult:
        return EvaluationCaseResult(
            case=case,
            failure_category=category,
            failure_reason=reason,
            **values,  # type: ignore[arg-type]
        )


def format_evaluation_report(report: EvaluationReport) -> str:
    metrics = report.metrics
    lines = [
        "DEVELOPMENT EVALUATION ONLY",
        "NOT COURSE RESULTS",
        "",
        f"Total questions: {metrics.total_questions}",
        f"Planning accuracy: {_format_metric(metrics.planning_accuracy)}",
        f"Answer accuracy: {_format_metric(metrics.answer_accuracy)}",
        f"Evidence accuracy: {_format_metric(metrics.evidence_accuracy)}",
        "Unsupported rejection accuracy: "
        f"{_format_metric(metrics.unsupported_rejection_accuracy)}",
        "",
        "Failures:",
    ]
    if not report.failures:
        lines.append("none")
    for result in report.failures:
        assert result.failure_category is not None
        lines.append(
            f"- {result.case.id} | {result.failure_category.value} | "
            f"{result.failure_reason}"
        )
    return "\n".join(lines)


def _format_metric(metric) -> str:
    if metric.percentage is None:
        return "n/a (0/0)"
    return f"{metric.percentage:.1f}% ({metric.correct}/{metric.total})"
