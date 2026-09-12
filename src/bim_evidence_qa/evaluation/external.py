"""Frozen IFC-Bench external-validation adapter.

This module deliberately does not alter planning, IFC parsing, or query execution.
It records the outcome of running a pre-classified held-out set and keeps cases that
are outside the frozen capability boundary out of system execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from bim_evidence_qa.answering import AnswerBuilder
from bim_evidence_qa.domain import QueryPlan
from bim_evidence_qa.parsers import IfcOpenShellParser
from bim_evidence_qa.query import (
    DevelopmentNaturalLanguagePlanner,
    IncompleteDataError,
    InvalidPlannerOutputError,
    QueryEngine,
    QueryExecutionError,
    UnsupportedQueryError,
)
from bim_evidence_qa.query.catalog import QueryCatalog


UNIT_TO_METERS = {
    "m": 1.0,
    "mm": 0.001,
    "cm": 0.01,
    "ft": 0.3048,
    "in": 0.0254,
}


def normalize_length(value: object, unit: object) -> float | None:
    """Convert a scalar length to metres using only an explicit unit."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not isinstance(unit, str):
        return None
    factor = UNIT_TO_METERS.get(unit.casefold().strip())
    return None if factor is None else float(value) * factor


def score_numeric(
    actual_value: object,
    actual_unit: object,
    expected: dict[str, object],
) -> dict[str, object]:
    """Score a numeric official value without inferring a missing unit."""
    expected_value = expected.get("value")
    expected_unit = expected.get("unit")
    tolerance = expected.get("absolute_tolerance")
    expected_m = normalize_length(expected_value, expected_unit)
    actual_m = normalize_length(actual_value, actual_unit)
    value_correct = (
        expected_m is not None
        and actual_m is not None
        and isinstance(tolerance, (int, float))
        and abs(actual_m - expected_m) <= float(tolerance)
    )
    return {
        "expected_value": expected_value,
        "expected_unit": expected_unit,
        "actual_value": actual_value,
        "actual_unit": actual_unit,
        "normalized_expected_m": expected_m,
        "normalized_actual_m": actual_m,
        "value_correct": value_correct,
        "unit_correct": actual_m is not None,
        "correct": value_correct,
    }


def _model_key(case: dict[str, object]) -> str:
    return str(case["model_path"])


def load_selected_models(
    cases: Iterable[dict[str, object]], cache: Path,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Parse every selected IFC once and retain load failures in the report."""
    datasets: dict[str, object] = {}
    loads: dict[str, dict[str, object]] = {}
    parser = IfcOpenShellParser()
    for model_path in sorted({_model_key(case) for case in cases}):
        source = cache / model_path
        record: dict[str, object] = {
            "model_path": model_path,
            "exists": source.is_file(),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest()
            if source.is_file() else None,
        }
        try:
            dataset = parser.parse(source)
        except Exception as error:  # Preserve parser failures as validation data.
            record.update({"status": "load_failure", "error": f"{type(error).__name__}: {error}"})
        else:
            datasets[model_path] = dataset
            record.update({"status": "loaded", "entity_count": len(dataset.entities)})
        loads[model_path] = record
    return datasets, loads


def _failure_category(error: Exception) -> str:
    if isinstance(error, InvalidPlannerOutputError):
        return "invalid_plan"
    if isinstance(error, UnsupportedQueryError):
        return "planner_operation_error"
    if isinstance(error, IncompleteDataError):
        return "missing_ifc_data"
    if isinstance(error, QueryExecutionError):
        return "execution_error"
    code = getattr(error, "code", None)
    if code == "entity_not_found":
        return "object_resolution_error"
    if code == "missing":
        return "property_resolution_error"
    if code == "ambiguous":
        return "property_resolution_error"
    return "execution_error"


def _actual_unit(result: object) -> str | None:
    properties = getattr(result, "properties", ())
    if len(properties) == 1:
        return properties[0].unit
    # Aggregate QueryResult intentionally has no property provenance or unit.
    return None


def run_development_planner(
    cases: list[dict[str, object]], cache: Path,
) -> dict[str, object]:
    """Run only frozen supported cases; all others remain explicit non-runs."""
    datasets, model_loads = load_selected_models(cases, cache)
    planner = DevelopmentNaturalLanguagePlanner()
    engine = QueryEngine()
    results: list[dict[str, object]] = []

    for case in cases:
        record: dict[str, object] = {
            "benchmark_id": case["benchmark_id"],
            "project": case["project"],
            "ifc_model": case["ifc_model"],
            "question": case["question"],
            "official_answer": case["official_answer"],
            "capability_category": case["capability_category"],
            "expected_support_status": case["expected_support_status"],
            "scoring_method": case["scoring_method"],
        }
        if case["expected_support_status"] != "supported":
            record.update({"run_status": "not_run_out_of_scope", "automatic_correct": None})
            results.append(record)
            continue
        dataset = datasets.get(_model_key(case))
        if dataset is None:
            record.update({
                "run_status": "model_load_failure",
                "automatic_correct": False,
                "failure_category": "model_schema_mismatch",
            })
            results.append(record)
            continue
        plan: QueryPlan | None = None
        try:
            plan = planner.plan(str(case["question"]), QueryCatalog.from_dataset(dataset))
            result = engine.execute(plan, dataset)
            answer = AnswerBuilder().build(plan, result)
        except Exception as error:
            record.update({
                "run_status": "failed",
                "error": f"{type(error).__name__}: {error}",
                "failure_category": _failure_category(error),
                "plan": asdict(plan) if plan else None,
                "automatic_correct": False,
            })
        else:
            record.update({
                "run_status": "completed",
                "plan": asdict(plan),
                "answer_status": answer.status,
                "actual_value": answer.value,
                "actual_unit": _actual_unit(result),
                "answer_text": answer.text,
            })
            method = case["scoring_method"]
            if method == "numeric":
                scoring = score_numeric(answer.value, _actual_unit(result), case["expected"] or {})
                record["scoring"] = scoring
                record["automatic_correct"] = scoring["correct"]
                if not scoring["correct"]:
                    record["failure_category"] = (
                        "unit_mismatch" if not scoring["unit_correct"] else "answer_mismatch"
                    )
            elif method == "data_refusal":
                record["automatic_correct"] = False
                record["failure_category"] = "answer_mismatch"
            else:
                record["automatic_correct"] = None
                record["manual_review_required"] = True
        results.append(record)

    supported = [r for r in results if r["expected_support_status"] == "supported"]
    scoreable = [r for r in supported if r["scoring_method"] != "manual_review_required"]
    correct = sum(r["automatic_correct"] is True for r in scoreable)
    refusal = [r for r in scoreable if r["scoring_method"] == "data_refusal"]
    correct_refusal = sum(r["automatic_correct"] is True for r in refusal)
    unsupported = [r for r in results if r["expected_support_status"] == "unsupported"]
    failure_counts = Counter(
        str(r["failure_category"])
        for r in supported if r.get("failure_category")
    )
    unsupported_categories = Counter(str(r["capability_category"]) for r in unsupported)
    return {
        "planner": "DevelopmentNaturalLanguagePlanner",
        "execution_scope": "Only pre-classified supported cases were executed. Unsupported cases are category-only non-runs.",
        "model_loads": model_loads,
        "metrics": {
            "total_external_questions": len(results),
            "supported_questions": len(supported),
            "unsupported_questions": len(unsupported),
            "coverage": len(supported) / len(results) if results else None,
            "scoreable_supported_questions": len(scoreable),
            "correct_supported_answers": correct,
            "supported_accuracy": correct / len(scoreable) if scoreable else None,
            "manual_review_required_supported": len(supported) - len(scoreable),
            "overall_end_to_end_success_lower_bound": correct / len(results) if results else None,
            "correct_refusal_count": correct_refusal,
            "correct_refusal_denominator": len(refusal),
            "unsupported_refusals_not_measured": len(unsupported),
            "parser_model_load_failures": sum(r["status"] != "loaded" for r in model_loads.values()),
        },
        "failure_category_counts": dict(sorted(failure_counts.items())),
        "unsupported_capability_category_counts": dict(sorted(unsupported_categories.items())),
        "results": results,
    }


def choose_language_cases(cases: list[dict[str, object]], seed: int = 20260912) -> list[str]:
    """Freeze at most ten supported IDs before any language execution."""
    ids = sorted(
        str(case["benchmark_id"])
        for case in cases if case["expected_support_status"] == "supported"
    )
    return sorted(random.Random(seed).sample(ids, min(10, len(ids))), key=int)


def run_language_subset(
    cases: list[dict[str, object]], cache: Path,
    selected_ids: set[str],
) -> dict[str, object]:
    """Reuse the same frozen adapter without changing planner behavior."""
    subset = [case for case in cases if str(case["benchmark_id"]) in selected_ids]
    report = run_development_planner(subset, cache)
    report["language_case_ids"] = sorted(selected_ids, key=int)
    return report


def _read_cases(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run frozen IFC-Bench external validation.")
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--language-ids-output", type=Path)
    parser.add_argument("--include-ids", type=Path)
    args = parser.parse_args(argv)
    cases = _read_cases(args.cases)
    if args.include_ids:
        frozen_ids = set(json.loads(args.include_ids.read_text(encoding="utf-8"))["ids"])
        cases = [case for case in cases if str(case["benchmark_id"]) in frozen_ids]
    report = run_development_planner(cases, args.cache)
    if args.language_ids_output:
        report["language_case_ids"] = choose_language_cases(cases)
        args.language_ids_output.write_text(
            json.dumps({"seed": 20260912, "ids": report["language_case_ids"]}, indent=2) + "\n",
            encoding="utf-8",
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
