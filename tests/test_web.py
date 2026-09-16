from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from bim_evidence_qa import web
from bim_evidence_qa.domain import BuildingDataset, BuildingEntity, PropertySource, PropertyValue
from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner, IncompleteDataError
from bim_evidence_qa.web import UI_TEXT, _ifc_warnings, select_project_source


def test_no_project_mode_has_no_dataset(synthetic_dataset):
    mode, dataset = select_project_source(
        real_dataset=None,
        has_real_upload=False,
        use_synthetic=False,
        synthetic_dataset=synthetic_dataset,
    )

    assert mode == "No Project"
    assert dataset is None


def test_synthetic_project_mode_is_explicit(synthetic_dataset):
    mode, dataset = select_project_source(
        real_dataset=None,
        has_real_upload=False,
        use_synthetic=True,
        synthetic_dataset=synthetic_dataset,
    )

    assert mode == "Synthetic Development Project"
    assert dataset is synthetic_dataset


def test_real_ifc_takes_priority_over_synthetic_mode(
    synthetic_dataset,
    development_ifc_dataset,
):
    mode, dataset = select_project_source(
        real_dataset=development_ifc_dataset,
        has_real_upload=True,
        use_synthetic=True,
        synthetic_dataset=synthetic_dataset,
    )

    assert mode == "Uploaded Real Project"
    assert dataset is development_ifc_dataset


def test_failed_real_upload_does_not_fall_back_to_synthetic(synthetic_dataset):
    mode, dataset = select_project_source(
        real_dataset=None,
        has_real_upload=True,
        use_synthetic=True,
        synthetic_dataset=synthetic_dataset,
    )

    assert mode == "Uploaded Real Project"
    assert dataset is None


def test_ui_copy_is_centralized_and_complete_for_both_locales():
    assert set(UI_TEXT) == {"zh", "en"}
    assert set(UI_TEXT["zh"]) == set(UI_TEXT["en"])
    assert all(UI_TEXT[locale][key] for locale in UI_TEXT for key in UI_TEXT[locale])


def test_ifc_warnings_follow_ui_locale(development_ifc_dataset):
    assert _ifc_warnings(development_ifc_dataset, "zh") == ("1 个房间缺少名称",)
    assert _ifc_warnings(development_ifc_dataset, "en") == (
        "1 space has no name",
    )


def test_app_defaults_to_chinese_llm_planner_without_runtime_errors():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(
        timeout=10
    )

    assert not list(app.exception)
    assert not app.toggle
    assert len(app.button_group) == 1
    assert not app.checkbox
    assert any("v0.3.0" in item.value for item in app.markdown)
    assert [tab.label for tab in app.tabs] == ["IFC证据", "图纸证据"]
    app.query_params["dev"] = "1"
    app.run()
    assert app.button_group[1].value == UI_TEXT["zh"]["llm_planner"]
    assert app.checkbox[0].value is False
    assert app.text_input[0].disabled is True


@pytest.mark.parametrize("locale", ("zh", "en"))
def test_incomplete_data_message_is_recorded_in_the_active_locale(
    monkeypatch,
    locale,
):
    session_state = {"chat_history": []}
    monkeypatch.setattr(web.st, "session_state", session_state)

    def raise_incomplete_data(*_args, **_kwargs):
        raise IncompleteDataError(
            field="MeasuredArea",
            target_kind="space",
            available_count=2,
            total_count=3,
            missing_entity_ids=("ifc-6",),
        )

    monkeypatch.setattr(web, "run_question", raise_incomplete_data)

    web._submit_question(locale, object(), object(), "largest space")

    assert session_state["chat_history"][0]["question"] == "largest space"
    assert session_state["chat_history"][0]["status"] == "error"
    assert "MeasuredArea" in session_state["chat_history"][0]["answer"]
    assert "available for 2 of 3 entities" in session_state["last_error_details"]


@pytest.mark.parametrize("code", ("missing", "ambiguous", "unsupported", "entity_not_found", "missing_data"))
@pytest.mark.parametrize("locale", ("zh", "en"))
def test_resolution_errors_use_locale_and_preserve_candidates(monkeypatch, synthetic_dataset, code, locale):
    from bim_evidence_qa.domain import ResolutionError
    state = {"chat_history": []}
    monkeypatch.setattr(web.st, "session_state", state)
    def fail(*args, **kwargs):
        raise ResolutionError(code, "Internal English diagnostic", ("Qto_Test.Area [#123]",))
    monkeypatch.setattr(web, "run_question", fail)
    web._submit_question(locale, synthetic_dataset, object(), "面积？")
    expected_key = "unsupported_query" if code == "unsupported" else code
    assert state["chat_history"][0]["answer"] != "Internal English diagnostic"
    assert state["chat_history"][0]["error_key"] == expected_key
    assert state["last_resolution_error"]["candidates"] == ["Qto_Test.Area [#123]"]


@pytest.mark.parametrize("locale", ("zh", "en"))
def test_unsupported_query_uses_specific_prototype_message(monkeypatch, synthetic_dataset, locale):
    from bim_evidence_qa.domain import UnsupportedQueryError

    state = {"chat_history": []}
    monkeypatch.setattr(web.st, "session_state", state)
    monkeypatch.setattr(
        web,
        "run_question",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(UnsupportedQueryError("Relationship query")),
    )

    web._submit_question(locale, synthetic_dataset, object(), "五块楼板都在哪里？")

    assert "门" in state["chat_history"][0]["answer"] if locale == "zh" else "doors" in state["chat_history"][0]["answer"]
    assert "project data" not in state["chat_history"][0]["answer"].casefold()


@pytest.mark.parametrize("locale", ("zh", "en"))
def test_missing_storey_data_uses_the_explicit_ifc_status(monkeypatch, locale):
    from bim_evidence_qa.domain import BuildingDataset, BuildingEntity
    from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner

    state = {"chat_history": []}
    monkeypatch.setattr(web.st, "session_state", state)
    dataset = BuildingDataset((BuildingEntity("beam-1", "beam"),))

    web._submit_question(locale, dataset, DevelopmentNaturalLanguagePlanner(), "有几层楼？")

    assert state["chat_history"][0]["answer"] == UI_TEXT[locale]["missing_storey_data"]
    assert state["last_resolution_error"]["code"] == "missing_storey_data"


def test_web_carries_one_verified_object_into_a_property_follow_up(monkeypatch):
    state = {"chat_history": []}
    monkeypatch.setattr(web.st, "session_state", state)
    dataset = BuildingDataset((
        BuildingEntity(
            "door-d101",
            "door",
            name="Door D101",
            properties=(PropertyValue(
                PropertySource.QUANTITY,
                "Qto_DoorBaseQuantities",
                "Width",
                0.9,
                unit="m",
            ),),
        ),
    ))
    planner = DevelopmentNaturalLanguagePlanner()

    web._submit_question("zh", dataset, planner, "Find Door D101")
    web._submit_question("zh", dataset, planner, "那它的宽度呢？")

    assert len(state["chat_history"]) == 2
    assert state["chat_history"][1]["outcome"].plan.requested_property == "width"
    assert "0.9 m" in state["chat_history"][1]["answer"]


def test_missing_property_guidance_names_the_object_and_available_fields():
    dataset = BuildingDataset((
        BuildingEntity(
            "door-d101",
            "door",
            name="Door D101",
            properties=(PropertyValue(
                PropertySource.QUANTITY,
                "Qto_DoorBaseQuantities",
                "Width",
                0.9,
                unit="m",
            ),),
        ),
    ))
    error = web.ResolutionError("missing", "Property 'color' is unavailable on 'Door D101'.")

    message = web._guided_resolution_message("zh", error, dataset)

    assert "Door D101" in message
    assert "color" in message
    assert "Width" in message


def test_missing_object_guidance_includes_the_reference():
    dataset = BuildingDataset((BuildingEntity("door-d101", "door", name="Door D101"),))
    error = web.ResolutionError("entity_not_found", "Entity not found: 'D999'.")

    assert "D999" in web._guided_resolution_message("zh", error, dataset)


def test_developer_toggle_preserves_debug_information_and_language_switch():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
    app.query_params["dev"] = "1"
    app.run()
    app.checkbox(key="use_synthetic").check().run()
    app.button_group(key="planner_mode_control_zh").set_value("开发规划器").run()
    app.text_input[0].set_value("How many rooms are there?")
    app.button[0].click().run()
    assert not app.exception
    assert len(app.json) == 2
    app.query_params.clear()
    app.run()
    assert not app.json
    assert len(app.tabs) == 2
    assert not app.checkbox
    assert "这个建筑共有 5 个房间。" in " ".join(x.value for x in app.markdown)
    app.button_group(key="ui_language").set_value("EN").run()
    assert "There are 5 spaces." in " ".join(x.value for x in app.markdown)
    app.query_params["dev"] = "1"
    app.run()
    assert len(app.json) == 2
    assert app.button_group(key="planner_mode_control_en").value == "Development Planner"


def test_unmatched_pdf_is_only_in_collapsed_manual_browser():
    app = AppTest.from_string("""
import fitz
import streamlit as st
from bim_evidence_qa.web import _render_drawing_panel
from bim_evidence_qa.parsers.pdf import PyMuPDFParser
from bim_evidence_qa.drawing import DrawingRetrieval
pdf = fitz.open()
pdf.new_page()
doc = PyMuPDFParser().parse_bytes(pdf.tobytes(), file_name="manual.pdf")
st.session_state['chat_history'] = [{'question': 'test'}]
st.session_state['drawing_retrieval'] = DrawingRetrieval((), 'No reliable drawing evidence found.')
_render_drawing_panel('zh', (doc,))
""").run()
    assert not app.exception
    assert not app.json
    manual = next(e for e in app.expander if e.label == "手动浏览图纸")
    assert manual.proto.expanded is False
    assert len(manual.get("image")) == len(app.get("image")) == 1
    assert any("未找到可靠" in c.value for c in app.caption)
    assert any("未建立证据关联" in c.value for c in manual.caption)


@pytest.mark.parametrize("operation", ("count", "filter", "aggregate", "find"))
def test_collection_drawings_are_examples_not_direct_evidence(operation):
    app = AppTest.from_string("""
import streamlit as st
import pymupdf
from bim_evidence_qa.application import ApplicationQueryResult
from bim_evidence_qa.answering import AnswerBuilder
from bim_evidence_qa.domain import QueryOperation, QueryPlan, QueryResult, AggregateFunction
from bim_evidence_qa.drawing import DrawingEvidence, DrawingRetrieval
from bim_evidence_qa.parsers.pdf import PyMuPDFParser
from bim_evidence_qa.web import _render_drawing_panel
op = QueryOperation(st.session_state['operation'])
kwargs = dict(aggregate_function=AggregateFunction.MAX, aggregate_field='area') if op == QueryOperation.AGGREGATE else {}
plan = QueryPlan(op, kind='wall', **kwargs)
result = QueryResult(op, (), 9)
st.session_state['last_outcome'] = ApplicationQueryResult('question', plan, result, AnswerBuilder().build(plan,result))
pdf = pymupdf.open(); pdf.new_page()
doc = PyMuPDFParser().parse_bytes(pdf.tobytes(), file_name='test.pdf')
st.session_state['drawing_retrieval'] = DrawingRetrieval((DrawingEvidence(doc.file_name,1,'Plans',(),10,'match','S202'),),'match')
_render_drawing_panel('zh',(doc,))
""")
    app.session_state['operation'] = operation
    app.run()
    assert not app.exception
    assert any('未找到可直接证明' in c.value for c in app.caption)
    assert not any(c.value == '相关图纸证据' for c in app.caption)
    examples = next(e for e in app.expander if e.label == '相关图纸示例')
    assert not examples.proto.expanded
    assert len(examples.get('image')) == 1
    assert any('不直接证明当前统计结果' in c.value for c in examples.caption)


def test_real_project_badge_is_hidden_in_classroom_mode(monkeypatch, synthetic_dataset):
    uploads = web.ParsedUploads((), synthetic_dataset, True, True, ('test',), ())
    monkeypatch.setattr(web, '_render_project_panel', lambda locale: uploads)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py').run()
    assert not app.toggle
    assert not any('真实项目' in x.value for x in app.markdown)
    assert not any(e.label == '开发设置' for e in app.expander)
