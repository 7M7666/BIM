import subprocess
import sys
from pathlib import Path

import pytest

from bim_evidence_qa import llm_smoke, web
from bim_evidence_qa.cli import DEFAULT_FIXTURE as CLI_FIXTURE
from bim_evidence_qa.domain import AggregateFunction, QueryOperation, QueryPlan
from bim_evidence_qa.evaluation.__main__ import DEFAULT_FIXTURE as EVALUATION_FIXTURE
from bim_evidence_qa.llm_smoke import DEFAULT_CASES, DEFAULT_IFC, SmokeCase
from bim_evidence_qa.query import UnsupportedQueryError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cloud_requirements_match_runtime_dependencies():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(
        encoding="utf-8"
    ).splitlines()

    assert requirements == [
        "ifcopenshell==0.8.5",
        "PyMuPDF==1.28.2",
        "streamlit==1.62.0",
    ]


def test_app_entrypoint_imports_src_package_in_isolated_mode():
    command = [
        sys.executable,
        "-I",
        "-c",
        (
            "import runpy; "
            f"namespace=runpy.run_path({str(PROJECT_ROOT / 'app.py')!r}, "
            "run_name='deployment_import_check'); "
            "import bim_evidence_qa; "
            "print(bim_evidence_qa.__file__)"
        ),
    ]

    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT.parent,
        check=True,
        capture_output=True,
        text=True,
    )

    assert str(PROJECT_ROOT / "src" / "bim_evidence_qa") in completed.stdout


def test_development_fixtures_do_not_depend_on_current_working_directory(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    assert web.SYNTHETIC_FIXTURE.is_file()
    assert CLI_FIXTURE.is_file()
    assert EVALUATION_FIXTURE.is_file()
    assert DEFAULT_IFC.is_file()


def test_default_llm_smoke_case_categories_match_report_denominators():
    unsupported = sum(case.expect_unsupported for case in DEFAULT_CASES)
    incomplete = sum(case.expect_incomplete_data for case in DEFAULT_CASES)

    assert len(DEFAULT_CASES) - unsupported == 21
    assert len(DEFAULT_CASES) - unsupported - incomplete == 18
    assert incomplete == 3
    assert unsupported == 7


def test_llm_smoke_case_cannot_expect_two_rejection_categories():
    with pytest.raises(ValueError, match="cannot expect both"):
        SmokeCase(
            "Ambiguous case",
            expect_unsupported=True,
            expect_incomplete_data=True,
        )


def test_llm_smoke_reports_expected_incomplete_data_as_pass(
    monkeypatch,
    capsys,
):
    cases_by_question = {case.question: case for case in DEFAULT_CASES}

    class DeterministicPlanner:
        def __init__(self, provider):
            pass

        def plan(self, question, catalog):
            case = cases_by_question[question]
            if case.expect_unsupported:
                raise UnsupportedQueryError("Not present in the query catalog.")
            if case.expect_incomplete_data:
                return QueryPlan(
                    operation=QueryOperation.AGGREGATE,
                    kind="space",
                    aggregate_function=AggregateFunction.MAX,
                    aggregate_field="DevelopmentSpaceQuantities.MeasuredArea",
                )
            return QueryPlan(operation=QueryOperation.COUNT, kind="space")

    monkeypatch.setattr(llm_smoke, "LLMQueryPlanner", DeterministicPlanner)
    monkeypatch.setenv("BIM_QA_LLM_API_KEY", "fake-test-key")
    monkeypatch.setenv(
        "BIM_QA_LLM_ENDPOINT",
        "https://api.deepseek.com/chat/completions",
    )
    monkeypatch.setenv("BIM_QA_LLM_MODEL", "deepseek-v4-flash")

    assert llm_smoke.main([]) == 0

    output = capsys.readouterr().out
    assert output.count("PASS | incomplete_data_detected") == 3
    assert "FAIL | incomplete_data" not in output
    assert "Valid plan generation: 21/21" in output
    assert "Complete-data grounded success: 18/18" in output
    assert "Incomplete-data detection: 3/3" in output
    assert "Unsupported rejection: 7/7" in output
