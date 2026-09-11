"""Course scoring alongside the unchanged synthetic evaluation path."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
import re
from pathlib import Path

from bim_evidence_qa.answering import AnswerBuilder
from bim_evidence_qa.query import QueryCatalog, QueryEngine, DevelopmentNaturalLanguagePlanner
from bim_evidence_qa.evaluation.schema import load_evaluation_cases
from bim_evidence_qa.parsers import IfcOpenShellParser


def equal_value(actual, expected):
    if isinstance(expected, (float, int)) and not isinstance(expected, bool):
        return isinstance(actual, (float, int)) and not isinstance(actual, bool) and math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-6)
    return actual == expected


def evaluate_course(planner, datasets, cases):
    catalogs = {key: QueryCatalog.from_dataset(value) for key, value in datasets.items()}
    rows = []
    for case in cases:
        plan = result = answer = None
        selected = ()
        status, message, candidates = "success", "", ()
        try:
            plan = planner.plan(case.question, catalogs[case.model])
            selected = QueryEngine()._select(plan, datasets[case.model])
            result = QueryEngine().execute(plan, datasets[case.model])
            answer = AnswerBuilder().build(plan, result)
            if answer.status == "not_found":
                status = "entity_not_found"
        except Exception as error:
            status = getattr(error, "code", "execution_error")
            message = f"{type(error).__name__}: {error}"
            candidates = getattr(error, "candidates", ())
        errors = []
        checks = {}
        if case.expected_operation is None:
            checks["planning"] = status == case.expected_status and plan is None
        else:
            parts = {
                "planner_operation_error": plan is not None and plan.operation == case.expected_operation,
                "planner_entity_error": plan is not None and plan.kind == case.expected_entity_type,
                "property_resolution_error": plan is not None and plan.requested_property == case.requested_property,
                "scope_resolution_error": plan is not None and [asdict(f) for f in plan.filters if f.field != "entity_id"] == list(case.expected_scope),
                "object_resolution_error": not case.expected_object_ids or {e.entity_id for e in selected} == set(case.expected_object_ids),
            }
            errors.extend(key for key, correct in parts.items() if not correct)
            checks["planning"] = all(parts.values())
        checks["status"] = status == case.expected_status
        checks["answer"] = checks["status"]
        checks["evidence"] = None
        if case.expected_status == "success":
            checks["answer"] = checks["status"] and answer is not None and equal_value(answer.value, case.expected_value) and {e.entity_id for e in result.entities} == set(case.expected_entity_ids)
            checks["evidence"] = answer is not None and {e.global_id for e in answer.evidence} == set(case.expected_global_ids)
            if case.expected_property_source:
                props = [p for e in answer.evidence for p in e.properties] if answer else []
                source_ok = len(props) == 1 and all((props[0].path if key == "path" else getattr(props[0], key)) == value for key, value in case.expected_property_source.items())
                unit_ok = len(props) == 1 and props[0].unit == case.expected_unit
                checks["evidence"] = checks["evidence"] and source_ok and unit_ok
                if not source_ok:
                    errors.append("property_resolution_error")
                if not unit_ok:
                    errors.append("unit_error")
        elif case.expected_candidates:
            checks["answer"] = checks["answer"] and {re.sub(r" \[#\d+\]$", "", c) for c in candidates} == set(case.expected_candidates)
        if not checks["status"]:
            errors.append({"missing": "missing_data", "ambiguous": "ambiguity_handling_error", "unsupported": "unsupported_handling_error", "entity_not_found": "object_resolution_error"}.get(case.expected_status, "answer_error"))
        if not checks["answer"]:
            errors.append("answer_error")
        if checks["evidence"] is False:
            errors.append("evidence_error")
        if not checks["planning"] and not errors:
            errors.append("unsupported_handling_error")
        rows.append({"case_id": case.id, "question": case.question, "expected": asdict(case),
                     "actual": {"status": status, "plan": asdict(plan) if plan else None, "value": answer.value if answer else None,
                                "answer": answer.text if answer else None, "object_ids": [e.entity_id for e in selected],
                                "evidence": [asdict(e) for e in answer.evidence] if answer else [], "candidates": candidates, "error": message},
                     "checks": checks, "fully_correct": all(v is not False for v in checks.values()),
                     "failure_type": sorted(set(errors)), "possible_cause": message or ("Compare the expected and actual structured fields listed above." if errors else None)})
    metrics = {}
    for key in ("planning", "answer", "evidence", "status"):
        applicable = [row["checks"][key] for row in rows if row["checks"][key] is not None]
        metrics[key] = {"correct": sum(applicable), "applicable_total": len(applicable), "accuracy": sum(applicable) / len(applicable) if applicable else None}
    fully = sum(r["fully_correct"] for r in rows)
    return {"planner": type(planner).__name__, "scoring": "Fixed ground-truth denominators. Planning, answer and status: all cases (correct refusal counts). Evidence: every expected success, including execution failures. Numeric rel_tol=1e-8, abs_tol=1e-6. Fully correct requires all applicable checks.",
            "total_cases": len(rows), "metrics": metrics, "fully_correct_cases": fully, "fully_correct_rate": fully / len(rows),
            "failure_count": len(rows) - fully, "error_category_counts": dict(Counter(t for r in rows for t in r["failure_type"])),
            "status_breakdown": {s: {"correct": sum(r["checks"]["status"] for r in rows if r["expected"]["expected_status"] == s), "total": sum(r["expected"]["expected_status"] == s for r in rows)} for s in sorted({c.expected_status for c in cases})},
            "failures": [r for r in rows if not r["fully_correct"]], "results": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-data", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=Path("tests/fixtures/course_cases.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", default="BIM-only baseline")
    parser.add_argument("--drawing-cases", type=Path)
    args = parser.parse_args()
    from bim_evidence_qa.evaluation.runner import EvaluationRunner
    datasets = {key: IfcOpenShellParser().parse(args.course_data / f"{key}_basic_sample_project.ifc") for key in ("rac", "rst")}
    report = EvaluationRunner(DevelopmentNaturalLanguagePlanner()).run_course(datasets, load_evaluation_cases(args.cases))
    report["label"] = args.label
    report["input_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.cases, *sorted(args.course_data.glob("*.ifc"))]}
    if args.drawing_cases:
        from bim_evidence_qa.parsers.pdf import PyMuPDFParser
        documents = {k: (PyMuPDFParser().parse(args.course_data / f"{k}_basic_sample_project.pdf"),) for k in datasets}
        report["drawing"] = evaluate_drawings(datasets, documents, load_evaluation_cases(args.cases), json.loads(args.drawing_cases.read_text(encoding="utf-8")))
        drawing_failures = {r["case_id"] for r in report["drawing"]["results"] if r["applicable"] and not r["correct"]}
        report["final_fully_correct_cases"] = sum(r["fully_correct"] and r["case_id"] not in drawing_failures for r in report["results"])
        report["final_fully_correct_rate"] = report["final_fully_correct_cases"] / len(report["results"])
        report["input_sha256"].update({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.drawing_cases, *sorted(args.course_data.glob("*.pdf"))]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"results", "failures"}}, indent=2))
    for row in report["failures"]:
        print(row["case_id"], row["question"], row["failure_type"], row["actual"]["error"])


def evaluate_drawings(datasets, documents, cases, drawing_cases):
    from bim_evidence_qa.application import run_question
    from bim_evidence_qa.drawing import retrieve_drawings
    lookup = {c.id: c for c in cases}
    rows = []
    for expected in drawing_cases:
        case = lookup[expected["case_id"]]
        actual, candidates, error = None, [], None
        try:
            outcome = run_question(datasets[case.model], case.question, DevelopmentNaturalLanguagePlanner())
            retrieval = retrieve_drawings(outcome, datasets[case.model], documents[case.model])
            actual = asdict(retrieval.best) if retrieval.best else None
            candidates = [asdict(c) for c in retrieval.candidates]
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        applicable = expected["expected_page"] is not None
        correct = error is None and (actual is not None and (actual["document"], actual["page_number"]) == (expected["expected_document"], expected["expected_page"]) if applicable else actual is None)
        rows.append({"case_id": case.id, "question": case.question, "expected": expected,
                     "actual": actual, "candidates": candidates, "applicable": applicable, "correct": correct,
                     "failure_type": [] if correct else ["drawing_retrieval_error"],
                     "possible_cause": error or (None if correct else "No confident candidate, or text ranking selected a different page.")})
    positives = [r for r in rows if r["applicable"]]
    controls = [r for r in rows if not r["applicable"]]
    return {"scoring": "Top-1=correct document AND 1-based page / all positive labels; abstentions on positive labels are failures. Coverage=non-abstained / positive labels. Negative controls reported separately, never credited to top-1. Related sheets do not prove numeric BIM answers or exact geometry.",
            "top1": {"correct": sum(r["correct"] for r in positives), "total": len(positives), "accuracy": sum(r["correct"] for r in positives) / len(positives)},
            "coverage": {"retrieved": sum(r["actual"] is not None for r in positives), "total": len(positives), "rate": sum(r["actual"] is not None for r in positives) / len(positives)},
            "no_match_controls": {"correct_abstentions": sum(r["correct"] for r in controls), "total": len(controls)},
            "failures": [r for r in rows if not r["correct"]], "results": rows}


if __name__ == "__main__":
    main()
