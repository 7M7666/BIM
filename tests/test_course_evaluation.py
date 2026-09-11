import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from test_phase2 import course_models
from bim_evidence_qa.evaluation.course import equal_value
from bim_evidence_qa.evaluation.course_ground_truth import build_cases
from bim_evidence_qa.evaluation.runner import EvaluationRunner
from bim_evidence_qa.evaluation.schema import load_evaluation_cases
from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner
from bim_evidence_qa.domain import QueryPlan, QueryOperation, UnsupportedQueryError

CASES = load_evaluation_cases(Path("tests/fixtures/course_cases.json"))


@pytest.fixture(scope="module")
def report(course_models):
    return EvaluationRunner(DevelopmentNaturalLanguagePlanner()).run_course({k: v[1] for k, v in course_models.items()}, CASES)


@pytest.mark.parametrize("index", range(len(CASES)), ids=[c.id for c in CASES])
def test_course_case(report, index):
    row = report["results"][index]
    assert row["fully_correct"], row


def test_raw_ground_truth_unchanged(course_models):
    assert build_cases(Path(os.environ["BIM_QA_COURSE_DATA"])) == json.loads(Path("tests/fixtures/course_cases.json").read_text(encoding="utf-8"))
    assert sum(c.language != "en" for c in CASES) >= len(CASES) // 3


@pytest.mark.parametrize("field,value,metric", [
    ("expected_entity_type", "window", "planning"),
    ("expected_operation", QueryOperation.COUNT, "planning"),
    ("requested_property", "height", "planning"),
    ("expected_scope", ({"field": "container_id", "operator": "eq", "value": "wrong"},), "planning"),
    ("expected_object_ids", ("wrong",), "planning"),
    ("expected_value", -999, "answer"),
    ("expected_global_ids", ("wrong",), "evidence"),
    ("expected_unit", "m", "evidence"),
    ("expected_property_source", {"field_name": "Wrong"}, "evidence"),
    ("expected_status", "missing", "status"),
])
def test_scorer_detects_structured_mismatch(course_models, field, value, metric):
    case = next(c for c in CASES if c.category == "property")
    altered = replace(case, **{field: value})
    result = EvaluationRunner(DevelopmentNaturalLanguagePlanner()).run_course({k: v[1] for k, v in course_models.items()}, (altered,))
    assert result["metrics"][metric]["correct"] == 0
    assert result["failure_count"] == 1


def test_early_failure_does_not_shrink_denominators(course_models):
    class Reject:
        def plan(self, question, catalog):
            raise UnsupportedQueryError("deliberate rejection")
    result = EvaluationRunner(Reject()).run_course({k: v[1] for k, v in course_models.items()}, CASES)
    assert result["metrics"]["planning"]["applicable_total"] == 48
    assert result["metrics"]["evidence"]["applicable_total"] == 39
    assert result["metrics"]["evidence"]["correct"] == 0
    assert result["failure_count"] == 43


def test_numeric_tolerance():
    assert equal_value(4242.600000001, 4242.6)
    assert not equal_value(4243, 4242.6)
    assert not equal_value(True, 1)
