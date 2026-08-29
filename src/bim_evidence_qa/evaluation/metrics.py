from dataclasses import dataclass

from bim_evidence_qa.evaluation.schema import EvaluationCaseResult


@dataclass(frozen=True, slots=True)
class MetricScore:
    correct: int
    total: int

    @property
    def percentage(self) -> float | None:
        return self.correct / self.total * 100 if self.total else None


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    total_questions: int
    planning_accuracy: MetricScore
    answer_accuracy: MetricScore
    evidence_accuracy: MetricScore
    unsupported_rejection_accuracy: MetricScore

    def as_dict(self) -> dict[str, object]:
        return {
            "total_questions": self.total_questions,
            "planning_accuracy": _metric_payload(self.planning_accuracy),
            "answer_accuracy": _metric_payload(self.answer_accuracy),
            "evidence_accuracy": _metric_payload(self.evidence_accuracy),
            "unsupported_rejection_accuracy": _metric_payload(
                self.unsupported_rejection_accuracy
            ),
        }


def calculate_metrics(
    results: tuple[EvaluationCaseResult, ...],
) -> EvaluationMetrics:
    return EvaluationMetrics(
        total_questions=len(results),
        planning_accuracy=_score(results, "planning_correct"),
        answer_accuracy=_score(results, "answer_correct"),
        evidence_accuracy=_score(results, "evidence_correct"),
        unsupported_rejection_accuracy=_score(
            results, "unsupported_rejected"
        ),
    )


def _score(
    results: tuple[EvaluationCaseResult, ...],
    field_name: str,
) -> MetricScore:
    values = [
        getattr(result, field_name)
        for result in results
        if getattr(result, field_name) is not None
    ]
    return MetricScore(correct=sum(value is True for value in values), total=len(values))


def _metric_payload(metric: MetricScore) -> dict[str, object]:
    return {
        "correct": metric.correct,
        "total": metric.total,
        "percentage": metric.percentage,
    }
