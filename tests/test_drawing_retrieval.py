import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_phase2 import course_models
from bim_evidence_qa.application import run_question
from bim_evidence_qa.domain import BuildingDataset, BuildingEntity, PropertyValue, PropertySource
from bim_evidence_qa.drawing import retrieve_drawings
from bim_evidence_qa.evaluation.course import evaluate_drawings
from bim_evidence_qa.evaluation.schema import load_evaluation_cases
from bim_evidence_qa.parsers.pdf import DrawingPage, DrawingDocument, PyMuPDFParser, sheet_identity
from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner

LABELS = json.loads(Path("tests/fixtures/course_drawing_cases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def drawing_report(course_models):
    folder = Path(os.environ["BIM_QA_COURSE_DATA"])
    documents = {k: (PyMuPDFParser().parse(folder / f"{k}_basic_sample_project.pdf"),) for k in course_models}
    return evaluate_drawings({k: v[1] for k, v in course_models.items()}, documents,
                             load_evaluation_cases(Path("tests/fixtures/course_cases.json")), LABELS)


@pytest.mark.parametrize("index", range(len(LABELS)), ids=[c["case_id"] for c in LABELS])
def test_real_drawing_case(drawing_report, index):
    assert drawing_report["results"][index]["correct"], drawing_report["results"][index]


def sample(texts, mark="103", name="Door:Type:123456"):
    entity = BuildingEntity("d", "door", name, "GLOBAL", properties=(PropertyValue(PropertySource.PSET, "Identity Data", "Mark", mark),))
    dataset = BuildingDataset((entity,))
    outcome = run_question(dataset, f"Find {name}", DevelopmentNaturalLanguagePlanner())
    document = DrawingDocument("drawing.pdf", tuple(DrawingPage(i + 1, text, "Plans", "A101") for i, text in enumerate(texts)), {}, b"")
    return dataset, outcome, document


@pytest.mark.parametrize("text", ["A103", "1103", "1030", "103.5", "x103", "103-2", "Door 103", "1\n3"])
def test_numeric_mark_does_not_match_substrings_or_dimensions(text):
    dataset, outcome, document = sample([text])
    assert retrieve_drawings(outcome, dataset, (document,)).best is None


def test_exact_mark_and_stronger_exported_id_ranking():
    dataset, outcome, document = sample(["103", "Door (123456)"])
    result = retrieve_drawings(outcome, dataset, (document,))
    assert result.best.page_number == 2
    assert result.candidates[1].page_number == 1
    assert result.best.matched_terms[0].entity_ids == ("d",)


def test_bare_numeric_dimension_is_not_an_element_identifier():
    dataset, outcome, document = sample(["123456 mm"])
    assert retrieve_drawings(outcome, dataset, (document,)).best is None


def test_tie_abstains_and_preserves_candidates():
    dataset, outcome, document = sample(["103", "103"])
    result = retrieve_drawings(outcome, dataset, (document,))
    assert result.best is None and len(result.candidates) == 2
    assert "Equal-score" in result.reason


def test_shared_type_requires_plan_context_and_repetition():
    entity = BuildingEntity("w", "window", "Window:Type:789000", properties=(PropertyValue(PropertySource.PSET, "Identity Data", "Type Mark", "46"),))
    dataset = BuildingDataset((entity,))
    outcome = run_question(dataset, "List all windows", DevelopmentNaturalLanguagePlanner())
    for text, title, matches in [("46", "Plans", False), ("46\n46\n46", None, False), ("46\n46\n46", "Floor Plans", True)]:
        doc = DrawingDocument("x.pdf", (DrawingPage(1, text, title),), {}, b"")
        result = retrieve_drawings(outcome, dataset, (doc,))
        assert bool(result.best) == matches
        if matches:
            assert "shared" in result.best.reason


def test_question_is_not_used_as_search_text():
    dataset, outcome, document = sample(["999999"])
    outcome = replace(outcome, question="Find 999999 in PDF")
    assert retrieve_drawings(outcome, dataset, (document,)).best is None


def test_title_only_from_explicit_text_not_page_number():
    assert sheet_identity("Level 2\nS201\n200UB25.4") == (None, None)
    assert sheet_identity("27/08/2026 2:14:20 PM\nFooting Detail\n001-00\nSample House\nAutodesk\nIssue Date\nAuthor\nChecker\nS204\n") == ("Footing Detail", "S204")


def test_drawing_failure_denominators(course_models):
    cases = load_evaluation_cases(Path("tests/fixtures/course_cases.json"))
    report = evaluate_drawings({k: v[1] for k, v in course_models.items()}, {k: () for k in course_models}, cases, LABELS)
    assert report["top1"] == {"correct": 0, "total": 10, "accuracy": 0}
    assert report["coverage"] == {"retrieved": 0, "total": 10, "rate": 0}
    assert len(report["failures"]) == 10
    assert report["no_match_controls"]["correct_abstentions"] == 2


def test_automatic_ui_page_selection_and_manual_override(course_models):
    folder = str(Path(os.environ["BIM_QA_COURSE_DATA"]))
    app = AppTest.from_string('''
import streamlit as st
from pathlib import Path
from bim_evidence_qa.web import _render_drawing_panel
from bim_evidence_qa.parsers.pdf import PyMuPDFParser
from bim_evidence_qa.drawing import DrawingEvidence, DrawingRetrieval
doc = PyMuPDFParser().parse(Path(st.session_state['folder']) / 'rac_basic_sample_project.pdf')
st.session_state['drawing_retrieval'] = DrawingRetrieval((DrawingEvidence(doc.file_name,3,'Plans',(),10,'test match','A102'),),'test match')
_render_drawing_panel('en',(doc,))
''')
    app.session_state["folder"] = folder
    app.run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="drawing_page_selector").value == 3
    app.selectbox(key="drawing_page_selector").select(4).run()
    assert app.selectbox(key="drawing_page_selector").value == 4
