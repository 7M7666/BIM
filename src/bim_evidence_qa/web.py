import os
from pathlib import Path

import streamlit as st

from bim_evidence_qa.application import ApplicationQueryResult, run_question
from bim_evidence_qa.domain import QueryPlan
from bim_evidence_qa.parsers import FixtureParseError, SyntheticFixtureParser
from bim_evidence_qa.query import (
    DevelopmentNaturalLanguagePlanner,
    InvalidPlannerOutputError,
    LLMProviderError,
    LLMProviderSettings,
    LLMQueryPlanner,
    MissingLLMConfigurationError,
    OpenAICompatibleChatProvider,
    UnsupportedQueryError,
)


SYNTHETIC_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "synthetic_project.json"
)


def main() -> None:
    st.set_page_config(page_title="BIM Evidence QA", page_icon="🏗️", layout="wide")
    st.title("BIM Evidence QA")
    st.caption(
        "Natural-language BIM question answering with verifiable entity evidence"
    )

    project_column, ask_column = st.columns([1, 2], gap="large")

    with project_column:
        st.subheader("PROJECT")
        _render_uploads()
        st.divider()
        use_synthetic = st.checkbox(
            "Development Mode: Use Synthetic Fixture",
            value=False,
        )
        planner_mode = st.selectbox(
            "Query planner",
            ("Development Planner", "LLM Planner"),
        )

        dataset = None
        if use_synthetic:
            st.error("SYNTHETIC DEVELOPMENT DATA\n\nNOT FOR EVALUATION")
            try:
                dataset = SyntheticFixtureParser().parse(SYNTHETIC_FIXTURE)
            except FixtureParseError as error:
                st.error(f"Synthetic fixture could not be loaded: {error}")
            else:
                st.success(f"Loaded {len(dataset.entities)} synthetic entities.")
        else:
            st.info(
                "No parsed project data. Enable synthetic development mode to ask "
                "questions while real IFC/PDF parsers are pending."
            )

        planner = _planner(planner_mode)

    with ask_column:
        st.subheader("ASK")
        enabled = dataset is not None and planner is not None
        with st.form("question_form"):
            question = st.text_input(
                "Natural-language question",
                placeholder="Which room has the largest area?",
                disabled=not enabled,
            )
            submitted = st.form_submit_button(
                "Ask project",
                disabled=not enabled,
            )

        if submitted and dataset is not None and planner is not None:
            try:
                outcome = run_question(dataset, question, planner)
            except (UnsupportedQueryError, InvalidPlannerOutputError) as error:
                st.session_state.pop("last_outcome", None)
                st.error(
                    "This query cannot be answered with the currently available "
                    "project data."
                )
                with st.expander("Developer error details"):
                    st.code(str(error))
            except LLMProviderError as error:
                st.session_state.pop("last_outcome", None)
                st.error("The configured LLM planner could not return a query plan.")
                with st.expander("Developer error details"):
                    st.code(str(error))
            else:
                st.session_state["last_outcome"] = outcome

        outcome = st.session_state.get("last_outcome") if enabled else None
        if isinstance(outcome, ApplicationQueryResult):
            _render_outcome(outcome)


def _render_uploads() -> None:
    drawing_files = st.file_uploader(
        "Upload Drawing (.pdf)",
        type=("pdf",),
        accept_multiple_files=True,
        key="drawing_upload",
    )
    ifc_file = st.file_uploader(
        "Upload BIM Model (.ifc)",
        type=("ifc",),
        key="ifc_upload",
    )

    upload_state = {
        "drawings": _file_metadata(drawing_files, ".pdf"),
        "ifc": _file_metadata([ifc_file] if ifc_file is not None else [], ".ifc"),
    }
    st.session_state["upload_state"] = upload_state

    for file_info in upload_state["drawings"]:
        st.write(f"📄 {file_info['name']} — {_format_bytes(file_info['size'])}")
    if upload_state["drawings"]:
        st.caption("PDF parser pending.")

    for file_info in upload_state["ifc"]:
        st.write(f"🏢 {file_info['name']} — {_format_bytes(file_info['size'])}")
    if upload_state["ifc"]:
        st.caption("IFC parser pending real course data.")


def _file_metadata(files: list, expected_suffix: str) -> list[dict[str, object]]:
    metadata = []
    for uploaded_file in files:
        if Path(uploaded_file.name).suffix.casefold() != expected_suffix:
            st.error(
                f"Rejected {uploaded_file.name}: expected a {expected_suffix} file."
            )
            continue
        metadata.append(
            {
                "name": uploaded_file.name,
                "size": uploaded_file.size,
                "extension": expected_suffix,
            }
        )
    return metadata


def _planner(mode: str):
    if mode == "Development Planner":
        st.caption("Offline development fallback — limited keyword coverage.")
        return DevelopmentNaturalLanguagePlanner()

    if not os.getenv("BIM_QA_LLM_API_KEY"):
        st.warning(
            "LLM API key is missing. Set BIM_QA_LLM_API_KEY or switch to "
            "Development Planner."
        )
        return None
    try:
        settings = LLMProviderSettings.from_environment()
    except MissingLLMConfigurationError as error:
        st.warning(f"LLM Planner is not fully configured: {error}")
        return None
    return LLMQueryPlanner(OpenAICompatibleChatProvider(settings))


def _render_outcome(outcome: ApplicationQueryResult) -> None:
    st.markdown("### Answer")
    st.write(outcome.answer.text)

    st.markdown("### Evidence")
    if not outcome.answer.evidence:
        st.info("No entity evidence was returned.")
    for evidence in outcome.answer.evidence:
        with st.container(border=True):
            st.write(evidence.name or evidence.entity_id)
            st.caption(f"kind: {evidence.kind}")
            if evidence.global_id is None:
                st.warning("GlobalId unavailable")
            else:
                st.code(evidence.global_id)
    for warning in outcome.answer.warnings:
        st.warning(warning)

    with st.expander("Developer Details"):
        st.markdown("**QueryPlan**")
        st.json(_plan_payload(outcome.plan))
        st.markdown("**QueryResult**")
        st.json(
            {
                "operation": outcome.result.operation.value,
                "value": outcome.result.value,
                "entity_ids": [
                    entity.entity_id for entity in outcome.result.entities
                ],
            }
        )


def _plan_payload(plan: QueryPlan) -> dict[str, object]:
    return {
        "operation": plan.operation.value,
        "kind": plan.kind,
        "name": plan.name,
        "filters": [
            {
                "field": condition.field,
                "operator": condition.operator.value,
                "value": condition.value,
            }
            for condition in plan.filters
        ],
        "aggregate_function": (
            plan.aggregate_function.value
            if plan.aggregate_function is not None
            else None
        ),
        "aggregate_field": plan.aggregate_field,
    }


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
