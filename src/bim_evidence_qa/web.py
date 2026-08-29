import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from bim_evidence_qa.application import ApplicationQueryResult, run_question
from bim_evidence_qa.domain import BuildingDataset, QueryPlan
from bim_evidence_qa.parsers import (
    DrawingDocument,
    IFCParseError,
    IfcOpenShellParser,
    PDFParseError,
    PyMuPDFParser,
    FixtureParseError,
    SyntheticFixtureParser,
    search_drawing_text,
)
from bim_evidence_qa.query import (
    DevelopmentNaturalLanguagePlanner,
    InvalidPlannerOutputError,
    LLMProviderError,
    LLMProviderSettings,
    LLMQueryPlanner,
    MissingLLMConfigurationError,
    OpenAICompatibleChatProvider,
    QueryExecutionError,
    UnsupportedQueryError,
)


SYNTHETIC_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "synthetic_project.json"
)


@dataclass(frozen=True, slots=True)
class ParsedUploads:
    drawings: tuple[DrawingDocument, ...]
    ifc_dataset: BuildingDataset | None
    has_real_upload: bool
    ifc_uploaded: bool
    project_key: tuple[object, ...]


def main() -> None:
    st.set_page_config(page_title="BIM Evidence QA", page_icon="🏗️", layout="wide")
    st.title("BIM Evidence QA")
    st.caption(
        "Natural-language BIM question answering with verifiable entity evidence"
    )

    project_column, ask_column = st.columns([1, 2], gap="large")

    with project_column:
        st.subheader("PROJECT")
        uploads = _render_uploads()
        st.divider()
        use_synthetic = st.checkbox(
            "Development Mode: Use Synthetic Fixture",
            value=False,
            disabled=uploads.has_real_upload,
        )
        planner_mode = st.selectbox(
            "Query planner",
            ("Development Planner", "LLM Planner"),
        )

        synthetic_dataset = None
        if use_synthetic and not uploads.has_real_upload:
            st.warning("Development Preview\n\nCourse Data Pack Not Loaded")
            st.error("SYNTHETIC DEVELOPMENT DATA\n\nNOT FOR EVALUATION")
            try:
                synthetic_dataset = SyntheticFixtureParser().parse(SYNTHETIC_FIXTURE)
            except FixtureParseError as error:
                st.error(f"Synthetic fixture could not be loaded: {error}")
            else:
                st.success(
                    f"Loaded {len(synthetic_dataset.entities)} synthetic entities."
                )

        data_source, dataset = select_project_source(
            real_dataset=uploads.ifc_dataset,
            has_real_upload=uploads.has_real_upload,
            use_synthetic=use_synthetic,
            synthetic_dataset=synthetic_dataset,
        )
        st.markdown(f"**Data Source:** {data_source}")
        if data_source == "No Project":
            st.info(
                "No project data. Upload a PDF or IFC, or enable synthetic "
                "development mode."
            )
        elif data_source == "Uploaded Real Project" and dataset is None:
            if uploads.ifc_uploaded:
                st.info("IFC-backed questions are unavailable until parsing succeeds.")
            else:
                st.info(
                    "Drawing search is available. Upload an IFC model for "
                    "IFC-backed questions."
                )

        planner = _planner(planner_mode)

        active_project_key = (data_source, uploads.project_key)
        if st.session_state.get("active_project_key") != active_project_key:
            st.session_state["active_project_key"] = active_project_key
            st.session_state.pop("last_outcome", None)

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
            except QueryExecutionError as error:
                st.session_state.pop("last_outcome", None)
                st.error(str(error))
            else:
                st.session_state["last_outcome"] = outcome

        outcome = st.session_state.get("last_outcome") if enabled else None
        if isinstance(outcome, ApplicationQueryResult):
            _render_outcome(outcome)


def _render_uploads() -> ParsedUploads:
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

    parsed_drawings = []
    project_key_parts: list[object] = []
    for uploaded_file in drawing_files:
        st.write(f"📄 {uploaded_file.name} — {_format_bytes(uploaded_file.size)}")
        source_bytes = uploaded_file.getvalue()
        project_key_parts.append(
            (
                uploaded_file.name,
                len(source_bytes),
                hashlib.sha256(source_bytes).hexdigest(),
            )
        )
        try:
            drawing = _parse_pdf_upload(uploaded_file.name, source_bytes)
        except PDFParseError as error:
            st.error(f"PDF parsing failed for {uploaded_file.name}: {error}")
        else:
            parsed_drawings.append(drawing)
            st.success("PDF parsed successfully")
            st.write(f"Pages: {drawing.page_count}")
            text_status = "available" if drawing.has_text_layer else "unavailable"
            st.write(f"Text layer: {text_status}")
            if not drawing.has_text_layer:
                st.warning("No extractable text detected.\n\nOCR is not enabled.")

    drawings = tuple(parsed_drawings)
    if drawings:
        _render_drawing_tools(drawings)

    ifc_dataset = None
    if ifc_file is not None:
        st.write(f"🏢 {ifc_file.name} — {_format_bytes(ifc_file.size)}")
        source_bytes = ifc_file.getvalue()
        project_key_parts.append(
            (
                ifc_file.name,
                len(source_bytes),
                hashlib.sha256(source_bytes).hexdigest(),
            )
        )
        try:
            ifc_dataset = _parse_ifc_upload(ifc_file.name, source_bytes)
        except IFCParseError as error:
            st.error(f"IFC parsing failed for {ifc_file.name}: {error}")
        else:
            st.success("IFC parsed successfully")
            counts = _entity_counts(ifc_dataset)
            st.write(f"Storeys: {counts['storey']}")
            st.write(f"Spaces: {counts['space']}")
            st.write(f"Doors: {counts['door']}")
            st.write(f"Windows: {counts['window']}")
            st.write(f"Walls: {counts['wall']}")
            for warning in _ifc_warnings(ifc_dataset):
                st.warning(warning)

    st.session_state["upload_state"] = {
        "drawings": [
            {"name": file.name, "size": file.size, "extension": ".pdf"}
            for file in drawing_files
        ],
        "ifc": (
            [
                {
                    "name": ifc_file.name,
                    "size": ifc_file.size,
                    "extension": ".ifc",
                }
            ]
            if ifc_file is not None
            else []
        ),
    }

    return ParsedUploads(
        drawings=drawings,
        ifc_dataset=ifc_dataset,
        has_real_upload=bool(drawing_files or ifc_file is not None),
        ifc_uploaded=ifc_file is not None,
        project_key=tuple(project_key_parts),
    )


@st.cache_data(show_spinner=False)
def _parse_pdf_upload(file_name: str, source_bytes: bytes) -> DrawingDocument:
    return PyMuPDFParser().parse_bytes(source_bytes, file_name=file_name)


@st.cache_data(show_spinner=False)
def _parse_ifc_upload(file_name: str, source_bytes: bytes) -> BuildingDataset:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as temporary:
            temporary.write(source_bytes)
            temporary_path = Path(temporary.name)
        return IfcOpenShellParser().parse(temporary_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _render_drawing_tools(drawings: tuple[DrawingDocument, ...]) -> None:
    st.markdown("### Drawing Preview")
    drawing_by_name = {drawing.file_name: drawing for drawing in drawings}
    selected_name = st.selectbox("Drawing", tuple(drawing_by_name))
    selected_drawing = drawing_by_name[selected_name]
    page_number = st.selectbox(
        "Page",
        tuple(range(1, selected_drawing.page_count + 1)),
    )
    try:
        preview = PyMuPDFParser().render_page(selected_drawing, page_number)
    except PDFParseError as error:
        st.error(f"Drawing preview failed: {error}")
    else:
        st.image(preview, caption=f"{selected_name} — page {page_number}")

    query_term = st.text_input(
        "Drawing text search",
        placeholder="Room 101",
    )
    if query_term.strip():
        matches = [
            (drawing.file_name, page.page_number)
            for drawing in drawings
            for page in search_drawing_text(drawing, query_term)
        ]
        if matches:
            st.write("Matching drawing pages")
            for file_name, matching_page in matches:
                st.write(f"{file_name} — page {matching_page}")
        else:
            st.info("No matching drawing pages.")


def _entity_counts(dataset: BuildingDataset) -> dict[str, int]:
    return {
        kind: sum(entity.kind == kind for entity in dataset.entities)
        for kind in ("storey", "space", "door", "window", "wall")
    }


def _ifc_warnings(dataset: BuildingDataset) -> tuple[str, ...]:
    warnings = []
    labels = {
        "storey": ("storey", "storeys"),
        "space": ("space", "spaces"),
        "door": ("door", "doors"),
        "window": ("window", "windows"),
        "wall": ("wall", "walls"),
    }
    for kind, (singular, plural) in labels.items():
        missing_names = sum(
            entity.kind == kind and entity.name is None
            for entity in dataset.entities
        )
        if missing_names:
            label = singular if missing_names == 1 else plural
            verb = "has" if missing_names == 1 else "have"
            warnings.append(f"{missing_names} {label} {verb} no name")
        if kind == "storey":
            continue
        missing_containers = sum(
            entity.kind == kind and entity.container_id is None
            for entity in dataset.entities
        )
        if missing_containers:
            label = singular if missing_containers == 1 else plural
            verb = "has" if missing_containers == 1 else "have"
            warnings.append(
                f"{missing_containers} {label} {verb} no spatial container"
            )
    return tuple(warnings)


def select_project_source(
    *,
    real_dataset: BuildingDataset | None,
    has_real_upload: bool,
    use_synthetic: bool,
    synthetic_dataset: BuildingDataset | None,
) -> tuple[str, BuildingDataset | None]:
    if has_real_upload:
        return "Uploaded Real Project", real_dataset
    if use_synthetic:
        return "Synthetic Development Project", synthetic_dataset
    return "No Project", None


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
