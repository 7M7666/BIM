from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from bim_evidence_qa import web
from bim_evidence_qa.query import IncompleteDataError
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

    def raise_incomplete_data(*_args):
        raise IncompleteDataError(
            field="MeasuredArea",
            target_kind="space",
            available_count=2,
            total_count=3,
            missing_entity_ids=("ifc-6",),
        )

    monkeypatch.setattr(web, "run_question", raise_incomplete_data)

    web._submit_question(locale, object(), object(), "largest space")

    assert session_state["chat_history"] == [
        {
            "question": "largest space",
            "answer": UI_TEXT[locale]["incomplete_data"],
            "status": "error",
        }
    ]
    assert "available for 2 of 3 entities" in session_state["last_error_details"]
