import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping

from bim_evidence_qa.domain import QueryOperation, QueryPlan, ScalarValue


class FailureCategory(str, Enum):
    PLANNING_ERROR = "planning_error"
    UNSUPPORTED_QUERY = "unsupported_query"
    EXECUTION_ERROR = "execution_error"
    ANSWER_ERROR = "answer_error"
    EVIDENCE_ERROR = "evidence_error"
    DATA_MISSING = "data_missing"


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    id: str
    question: str
    expected_operation: QueryOperation | None
    expected_value: ScalarValue
    expected_entity_ids: tuple[str, ...]
    expected_global_ids: tuple[str, ...]
    category: str
    expect_unsupported: bool = False

    def __post_init__(self) -> None:
        for field_name in ("id", "question", "category"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Evaluation case {field_name} must be non-empty.")
        if not isinstance(self.expect_unsupported, bool):
            raise ValueError("Evaluation case expect_unsupported must be boolean.")
        if self.expect_unsupported:
            if self.expected_operation is not None:
                raise ValueError(
                    "Unsupported evaluation cases cannot expect an operation."
                )
            if (
                self.expected_value is not None
                or self.expected_entity_ids
                or self.expected_global_ids
            ):
                raise ValueError(
                    "Unsupported evaluation cases cannot expect facts or evidence."
                )
        elif not isinstance(self.expected_operation, QueryOperation):
            raise ValueError(
                "Supported evaluation cases require an expected operation."
            )
        if not self._is_scalar(self.expected_value):
            raise ValueError("Evaluation case expected_value must be scalar.")
        self._validate_ids("expected_entity_ids", self.expected_entity_ids)
        self._validate_ids("expected_global_ids", self.expected_global_ids)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "EvaluationCase":
        required = {
            "id",
            "question",
            "expected_operation",
            "expected_value",
            "expected_entity_ids",
            "expected_global_ids",
            "category",
        }
        allowed = required | {"expect_unsupported"}
        missing = required - payload.keys()
        unknown = payload.keys() - allowed
        if missing:
            raise ValueError(
                "Evaluation case is missing fields: " + ", ".join(sorted(missing))
            )
        if unknown:
            raise ValueError(
                "Evaluation case has unknown fields: " + ", ".join(sorted(unknown))
            )

        raw_operation = payload["expected_operation"]
        try:
            operation = (
                None
                if raw_operation is None
                else QueryOperation(raw_operation)
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid expected operation: {raw_operation}."
            ) from error

        return cls(
            id=payload["id"],  # type: ignore[arg-type]
            question=payload["question"],  # type: ignore[arg-type]
            expected_operation=operation,
            expected_value=payload["expected_value"],  # type: ignore[arg-type]
            expected_entity_ids=cls._ids_from_value(
                "expected_entity_ids", payload["expected_entity_ids"]
            ),
            expected_global_ids=cls._ids_from_value(
                "expected_global_ids", payload["expected_global_ids"]
            ),
            category=payload["category"],  # type: ignore[arg-type]
            expect_unsupported=payload.get("expect_unsupported", False),  # type: ignore[arg-type]
        )

    @staticmethod
    def _ids_from_value(field_name: str, value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise ValueError(f"Evaluation case {field_name} must be a list.")
        return tuple(value)  # type: ignore[arg-type]

    @staticmethod
    def _validate_ids(field_name: str, values: object) -> None:
        if not isinstance(values, tuple) or not all(
            isinstance(value, str) and value for value in values
        ):
            raise ValueError(
                f"Evaluation case {field_name} must contain non-empty strings."
            )

    @staticmethod
    def _is_scalar(value: object) -> bool:
        return value is None or isinstance(value, (str, int, float, bool))


@dataclass(frozen=True, slots=True)
class EvaluationCaseResult:
    case: EvaluationCase
    plan: QueryPlan | None = None
    actual_value: ScalarValue = None
    actual_entity_ids: tuple[str, ...] = ()
    actual_global_ids: tuple[str | None, ...] = ()
    planning_correct: bool | None = None
    answer_correct: bool | None = None
    evidence_correct: bool | None = None
    unsupported_rejected: bool | None = None
    failure_category: FailureCategory | None = None
    failure_reason: str | None = None


def load_evaluation_cases(path: Path) -> tuple[EvaluationCase, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Evaluation file must contain a JSON array.")
    return tuple(
        EvaluationCase.from_mapping(item)
        if isinstance(item, dict)
        else _invalid_case(index)
        for index, item in enumerate(payload)
    )


def _invalid_case(index: int) -> EvaluationCase:
    raise ValueError(f"Evaluation case at index {index} must be an object.")
