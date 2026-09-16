import hashlib
import base64
import html
import os
import re
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path

import streamlit as st

from bim_evidence_qa import __version__
from bim_evidence_qa.answering import AnswerBuilder
from bim_evidence_qa.application import (
    ApplicationQueryResult,
    ConversationContext,
    run_question,
)
from bim_evidence_qa.domain import BuildingDataset, QueryOperation, QueryPlan, ResolutionError
from bim_evidence_qa.drawing import retrieve_drawings
from bim_evidence_qa.parsers import (
    DrawingDocument,
    FixtureParseError,
    IFCParseError,
    IfcOpenShellParser,
    PDFParseError,
    PyMuPDFParser,
    SyntheticFixtureParser,
    search_drawing_text,
)
from bim_evidence_qa.query import (
    DevelopmentNaturalLanguagePlanner,
    IncompleteDataError,
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

UI_TEXT = {
    "zh": {
        "statistical_drawing_note": "当前回答来自 IFC 模型统计，未找到可直接证明该统计结果的单一图纸页。",
        "drawing_examples": "相关图纸示例",
        "drawing_example_note": "该页面用于展示相关构件，不直接证明当前统计结果。",

        "development_mode": "开发模式",
        "missing": "该对象的 IFC 数据中没有找到这个属性。",
        "entity_not_found": "没有找到对应的 BIM 对象。",
        "ambiguous": "存在多个可能匹配的对象或字段，无法唯一确定。请选择下方具体候选。",
        "unsupported": "当前版本暂不支持这种查询。",
        "missing_data": "已理解这个问题，但当前 IFC 中缺少回答所需的可验证数据。",
        "understood_but_unavailable": "已理解该问题，但当前项目中没有对应的可用 IFC 数据。",
        "missing_storey_data": "当前 IFC 模型中没有 IfcBuildingStorey 楼层实体，因此无法从空间层级确定建筑楼层数。",
        "manual_drawings": "手动浏览图纸",
        "manual_note": "手动浏览内容与当前答案未建立证据关联。",
        "no_reliable_drawing": "未找到可靠的对应图纸证据。",
        "ifc_answer_source": "当前回答仍来自 IFC 模型数据。",
        "related_drawing": "相关图纸证据",
        "match_details": "查看匹配详情",
        "match_basis": "匹配依据",
        "source": "证据来源",
        "set": "属性 / 工程量集",
        "field": "字段",
        "value": "数值",
        "unit": "单位",
        "unit_unavailable": "单位不可用",
        "unnamed": "未命名对象",
        "candidate": "候选对象或字段",

        "development_preview": "开发预览",
        "course_data_not_loaded": "尚未加载课程数据",
        "project": "项目",
        "drawing": "图纸",
        "upload_drawing": "上传 PDF",
        "bim_model": "BIM 模型",
        "upload_model": "上传 IFC",
        "choose_file": "选择文件",
        "files": "文件",
        "model_summary": "模型概况",
        "storeys": "楼层",
        "spaces": "房间",
        "doors": "门",
        "windows": "窗",
        "walls": "墙",
        "no_file_uploaded": "尚未上传文件",
        "synthetic_mode": "合成开发模式",
        "development_settings": "开发设置",
        "synthetic_warning": "合成开发数据，仅用于开发测试",
        "real_project": "真实项目",
        "synthetic_project": "开发数据",
        "no_project_badge": "未加载项目",
        "planner": "查询规划器",
        "llm_planner": "LLM 规划器",
        "development_planner": "开发规划器",
        "development_planner_note": "开发规划器支持基础中文、英文及混合查询；复杂表达可能不支持。",
        "assistant_title": "向这个建筑提问",
        "empty_title": "向这个建筑提问",
        "empty_description": "上传图纸和 BIM 模型后，\n可以直接使用自然语言查询建筑信息。",
        "question_placeholder": "输入关于当前建筑的问题...",
        "send": "发送",
        "thinking": "正在处理...",
        "unsupported_query": "当前版本暂不支持这种查询。",
        "incomplete_data": "已理解这个问题，但当前 IFC 中缺少回答所需的可验证数据。",
        "no_project": "请上传项目文件或启用开发模式后开始提问。",
        "ready_to_ask": "项目已就绪，请输入一个建筑问题。",
        "llm_key_missing": "尚未配置 LLM API Key。请配置云端 Secrets，或切换到开发规划器。",
        "llm_config_incomplete": "LLM 配置不完整。",
        "llm_request_failed": "LLM 规划器暂时无法返回查询计划。",
        "needs_context": "请说明要查询的具体对象或构件类型。",
        "ifc_evidence": "IFC证据",
        "drawing_evidence": "图纸证据",
        "query_details": "查询详情",
        "global_id": "GlobalId",
        "entity_type": "类型",
        "no_ifc_evidence": "暂无 IFC 证据",
        "entity_count": "{count} 个实体",
        "no_drawing_evidence": "暂无图纸证据",
        "no_query_details": "暂无查询信息",
        "query_plan": "查询计划",
        "query_result": "查询结果",
        "developer_error": "错误详情",
        "global_id_unavailable": "GlobalId 不可用",
        "pages": "页数",
        "page": "页",
        "search_drawing": "搜索图纸",
        "search_placeholder": "搜索图纸文本...",
        "no_text_layer": "未检测到可提取文本，当前未启用 OCR。",
        "text_layer_available": "文字层可用",
        "text_layer_unavailable": "文字层不可用",
        "pdf_parse_failed": "PDF 解析失败",
        "drawing_preview_failed": "图纸预览失败",
        "matching_pages": "匹配页面",
        "no_matching_pages": "没有匹配的图纸页面",
        "ifc_parse_failed": "IFC 解析失败",
        "model_unavailable": "—",
        "missing_name_one": "{count} 个{kind}缺少名称",
        "missing_name_many": "{count} 个{kind}缺少名称",
        "missing_container_one": "{count} 个{kind}缺少空间容器",
        "missing_container_many": "{count} 个{kind}缺少空间容器",
    },
    "en": {
        "statistical_drawing_note": "The answer comes from IFC model statistics. No single drawing page directly proves this result.",
        "drawing_examples": "Related drawing examples",
        "drawing_example_note": "This page illustrates related elements; it does not directly prove the statistical result.",

        "development_mode": "Developer mode",
        "missing": "The property was not found in this object’s IFC data.",
        "entity_not_found": "No matching BIM object was found.",
        "ambiguous": "Multiple objects or fields match. Please choose a specific candidate below.",
        "unsupported": "This query type is not supported by the current prototype.",
        "missing_data": "The question is understood, but verifiable IFC data needed to answer it is missing.",
        "understood_but_unavailable": "The question is understood, but this project has no corresponding IFC data available.",
        "missing_storey_data": "This IFC model has no IfcBuildingStorey entities, so its storey count cannot be determined from spatial hierarchy.",
        "manual_drawings": "Browse drawings manually",
        "manual_note": "Manual browsing is not linked as evidence for the current answer.",
        "no_reliable_drawing": "No reliable drawing evidence found.",
        "ifc_answer_source": "The answer remains grounded in IFC model data.",
        "related_drawing": "Related drawing evidence",
        "match_details": "Drawing match details",
        "match_basis": "Match basis",
        "source": "Evidence Source",
        "set": "Set",
        "field": "Field",
        "value": "Value",
        "unit": "Unit",
        "unit_unavailable": "unit unavailable",
        "unnamed": "Unnamed object",
        "candidate": "Candidate object or field",

        "development_preview": "Development Preview",
        "course_data_not_loaded": "Course Data Not Loaded",
        "project": "Project",
        "drawing": "Drawing",
        "upload_drawing": "Upload PDF",
        "bim_model": "BIM Model",
        "upload_model": "Upload IFC",
        "choose_file": "Choose file",
        "files": "Files",
        "model_summary": "Model Summary",
        "storeys": "Storeys",
        "spaces": "Spaces",
        "doors": "Doors",
        "windows": "Windows",
        "walls": "Walls",
        "no_file_uploaded": "No file uploaded",
        "synthetic_mode": "Synthetic Development Mode",
        "development_settings": "Development Settings",
        "synthetic_warning": "Synthetic development data — not for evaluation",
        "real_project": "Real project",
        "synthetic_project": "Development data",
        "no_project_badge": "No project",
        "planner": "Query planner",
        "llm_planner": "LLM Planner",
        "development_planner": "Development Planner",
        "development_planner_note": "The development planner supports basic Chinese, English and mixed queries; complex phrasing may be unsupported.",
        "assistant_title": "Ask About This Building",
        "empty_title": "Ask about this building",
        "empty_description": "Upload drawings and a BIM model,\nthen ask questions in natural language.",
        "question_placeholder": "Ask about the current building...",
        "send": "Send",
        "thinking": "Processing...",
        "unsupported_query": "This query type is not supported by the current prototype.",
        "incomplete_data": "The question is understood, but verifiable IFC data needed to answer it is missing.",
        "no_project": "Upload a project or enable development mode to start asking questions.",
        "ready_to_ask": "The project is ready. Ask a question about the building.",
        "llm_key_missing": "The LLM API key is not configured. Add Cloud Secrets or use the development planner.",
        "llm_config_incomplete": "The LLM configuration is incomplete.",
        "llm_request_failed": "The LLM planner could not return a query plan.",
        "needs_context": "Specify the object or entity type you want to query.",
        "ifc_evidence": "IFC Evidence",
        "drawing_evidence": "Drawing Evidence",
        "query_details": "Query",
        "global_id": "GlobalId",
        "entity_type": "Type",
        "no_ifc_evidence": "No IFC evidence available",
        "entity_count": "{count} entities",
        "no_drawing_evidence": "No drawing evidence available",
        "no_query_details": "No query details available",
        "query_plan": "QueryPlan",
        "query_result": "QueryResult",
        "developer_error": "Error details",
        "global_id_unavailable": "GlobalId unavailable",
        "pages": "Pages",
        "page": "Page",
        "search_drawing": "Search Drawing",
        "search_placeholder": "Search extracted drawing text...",
        "no_text_layer": "No extractable text detected. OCR is not enabled.",
        "text_layer_available": "Text layer available",
        "text_layer_unavailable": "Text layer unavailable",
        "pdf_parse_failed": "PDF parsing failed",
        "drawing_preview_failed": "Drawing preview failed",
        "matching_pages": "Matching pages",
        "no_matching_pages": "No matching drawing pages",
        "ifc_parse_failed": "IFC parsing failed",
        "model_unavailable": "—",
        "missing_name_one": "{count} {kind} has no name",
        "missing_name_many": "{count} {kind} have no name",
        "missing_container_one": "{count} {kind} has no spatial container",
        "missing_container_many": "{count} {kind} have no spatial container",
    },
}


@dataclass(frozen=True, slots=True)
class ParsedUploads:
    drawings: tuple[DrawingDocument, ...]
    ifc_dataset: BuildingDataset | None
    has_real_upload: bool
    ifc_uploaded: bool
    project_key: tuple[object, ...]
    file_rows: tuple[tuple[str, int], ...]


def _sync_planner_mode(control_key: str, locale: str) -> None:
    planner_mode = (
        "llm"
        if st.session_state[control_key] == _text(locale, "llm_planner")
        else "development"
    )
    st.session_state["_planner_mode"] = planner_mode


def main() -> None:
    st.set_page_config(page_title="BIM Evidence QA", layout="wide")
    st.session_state.setdefault("ui_language", "中文")
    locale = "zh" if st.session_state["ui_language"] == "中文" else "en"
    _inject_styles(locale)
    _render_header(locale)

    with st.container(key="workspace"):
        project_column, assistant_column, evidence_column = st.columns(
            [0.19, 0.53, 0.28],
            gap=None,
            vertical_alignment="top",
        )

        with project_column:
            with st.container(key="project_panel"):
                uploads = _render_project_panel(locale)
                development_mode = st.query_params.get("dev") == "1"
                st.session_state["development_mode"] = development_mode
                use_synthetic = st.session_state.get("_use_synthetic", False)
                planner_mode = st.session_state.get("_planner_mode", os.getenv("BIM_QA_UI_PLANNER", "llm"))
                if development_mode:
                    with st.expander(_text(locale, "development_settings"), expanded=False):
                        use_synthetic = st.checkbox(
                            _text(locale, "synthetic_mode"),
                            value=use_synthetic,
                            disabled=uploads.has_real_upload,
                            key="use_synthetic",
                        )
                        planner_control_key = f"planner_mode_control_{locale}"
                        st.session_state.setdefault("_planner_mode", planner_mode)
                        planner_labels = {
                            "llm": _text(locale, "llm_planner"),
                            "development": _text(locale, "development_planner"),
                        }
                        st.session_state.setdefault(
                            planner_control_key,
                            planner_labels[st.session_state["_planner_mode"]],
                        )
                        planner_label = st.segmented_control(
                            _text(locale, "planner"),
                            tuple(planner_labels.values()),
                            key=planner_control_key,
                            on_change=_sync_planner_mode,
                            args=(planner_control_key, locale),
                        )
                        planner_mode = next(
                            mode
                            for mode, label in planner_labels.items()
                            if label == planner_label
                        )
                        st.session_state["_planner_mode"] = planner_mode
                    st.session_state["_use_synthetic"] = use_synthetic
                synthetic_dataset = _load_synthetic_dataset(
                    locale,
                    use_synthetic=use_synthetic,
                    has_real_upload=uploads.has_real_upload,
                )
                data_source, dataset = select_project_source(
                    real_dataset=uploads.ifc_dataset,
                    has_real_upload=uploads.has_real_upload,
                    use_synthetic=use_synthetic,
                    synthetic_dataset=synthetic_dataset,
                )
                if development_mode or data_source == "Synthetic Development Project":
                    _render_project_mode_badge(locale, data_source)
                if dataset is not None:
                    for warning in _ifc_warnings(dataset, locale):
                        _status(warning, "neutral")
                planner = _planner(planner_mode, locale)

        active_project_key = (data_source, uploads.project_key)
        if st.session_state.get("active_project_key") != active_project_key:
            st.session_state["active_project_key"] = active_project_key
            st.session_state.pop("last_outcome", None)
            st.session_state.pop("last_error_details", None)
            st.session_state.pop("last_resolution_error", None)
            st.session_state["chat_history"] = []
            st.session_state.pop("conversation_context", None)
        st.session_state.setdefault("chat_history", [])

        with assistant_column:
            with st.container(key="assistant_panel"):
                _render_assistant_panel(locale, dataset, planner)

        with evidence_column:
            with st.container(key="evidence_panel"):
                outcome = st.session_state.get("last_outcome")
                st.session_state["drawing_retrieval"] = (
                    retrieve_drawings(outcome, dataset, uploads.drawings)
                    if isinstance(outcome, ApplicationQueryResult) and dataset is not None else None
                )
                _render_evidence_panel(locale, uploads.drawings)


def _render_header(locale: str) -> None:
    with st.container(key="app_header"):
        title_column, status_column, language_column = st.columns(
            [5.8, 2.6, 1.2],
            gap="small",
            vertical_alignment="center",
        )
        with title_column:
            st.markdown(
                "<div class='product-lockup'>"
                "<div class='product-title'>BIM Evidence QA "
                f"<span class='product-version'>v{__version__}</span></div>"
                f"<div class='product-subtitle'>{'BIM证据问答' if locale == 'zh' else 'BIM Evidence QA'}</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        with status_column:
            st.markdown(
                "<div class='header-status'><span></span>"
                f"{html.escape(('课堂演示' if locale == 'zh' else 'Classroom Demo'))}</div>",
                unsafe_allow_html=True,
            )
        with language_column:
            st.segmented_control(
                "Language",
                ("中文", "EN"),
                key="ui_language",
                label_visibility="collapsed",
            )


def _render_project_panel(locale: str) -> ParsedUploads:
    st.markdown(
        f"<div class='panel-title'>{html.escape(_text(locale, 'project'))}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='section-label'>{html.escape(_text(locale, 'drawing'))}</div>",
        unsafe_allow_html=True,
    )
    drawing_files = st.file_uploader(
        _text(locale, "upload_drawing"),
        type=("pdf",),
        accept_multiple_files=True,
        key="drawing_upload",
        label_visibility="collapsed",
    )
    st.markdown(
        f"<div class='section-label'>{html.escape(_text(locale, 'bim_model'))}</div>",
        unsafe_allow_html=True,
    )
    ifc_file = st.file_uploader(
        _text(locale, "upload_model"),
        type=("ifc",),
        key="ifc_upload",
        label_visibility="collapsed",
    )

    parsed_drawings = []
    project_key_parts: list[object] = []
    file_rows = []
    for uploaded_file in drawing_files:
        source_bytes = uploaded_file.getvalue()
        file_rows.append((uploaded_file.name, uploaded_file.size))
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
            _status(
                f"{_text(locale, 'pdf_parse_failed')}: {error}",
                "warning",
            )
        else:
            parsed_drawings.append(drawing)

    ifc_dataset = None
    if ifc_file is not None:
        source_bytes = ifc_file.getvalue()
        file_rows.append((ifc_file.name, ifc_file.size))
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
            _status(
                f"{_text(locale, 'ifc_parse_failed')}: {error}",
                "warning",
            )

    drawings = tuple(parsed_drawings)
    _render_model_summary(locale, ifc_dataset)

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
        file_rows=tuple(file_rows),
    )


def _render_file_rows(
    locale: str,
    file_rows: tuple[tuple[str, int], ...],
    drawings: tuple[DrawingDocument, ...],
) -> None:
    st.markdown(
        f"<div class='section-label'>{html.escape(_text(locale, 'files'))}</div>",
        unsafe_allow_html=True,
    )
    if not file_rows:
        st.markdown(
            f"<div class='empty-inline'>{html.escape(_text(locale, 'no_file_uploaded'))}</div>",
            unsafe_allow_html=True,
        )
        return

    drawing_names = {drawing.file_name for drawing in drawings}
    rows = []
    for name, size in file_rows:
        meta = _format_bytes(size)
        if name in drawing_names:
            drawing = next(item for item in drawings if item.file_name == name)
            meta = f"{drawing.page_count} {_text(locale, 'pages').casefold()} · {meta}"
        rows.append(
            "<div class='file-row'>"
            f"<span title='{html.escape(name, quote=True)}'>{html.escape(name)}</span>"
            f"<small>{html.escape(meta)}</small>"
            "</div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def _render_model_summary(
    locale: str,
    dataset: BuildingDataset | None,
) -> None:
    st.markdown(
        f"<div class='section-label'>{html.escape(_text(locale, 'model_summary'))}</div>",
        unsafe_allow_html=True,
    )
    if dataset is None:
        st.markdown(
            f"<div class='empty-inline'>{html.escape(_text(locale, 'model_unavailable'))}</div>",
            unsafe_allow_html=True,
        )
        return

    counts = _entity_counts(dataset)
    rows = "".join(
        "<div class='stat-row'>"
        f"<strong>{counts[kind]}</strong>"
        f"<span>{html.escape(_text(locale, label))}</span>"
        "</div>"
        for kind, label in (
            ("storey", "storeys"),
            ("space", "spaces"),
            ("door", "doors"),
            ("window", "windows"),
            ("wall", "walls"),
        )
    )
    st.markdown(f"<div class='stat-list'>{rows}</div>", unsafe_allow_html=True)


def _load_synthetic_dataset(
    locale: str,
    *,
    use_synthetic: bool,
    has_real_upload: bool,
) -> BuildingDataset | None:
    if not use_synthetic or has_real_upload:
        return None
    try:
        dataset = SyntheticFixtureParser().parse(SYNTHETIC_FIXTURE)
    except FixtureParseError as error:
        _status(str(error), "warning")
        return None
    _status(_text(locale, "synthetic_warning"), "warning")
    return dataset


def _render_project_mode_badge(locale: str, data_source: str) -> None:
    label = {
        "Uploaded Real Project": _text(locale, "real_project"),
        "Synthetic Development Project": _text(locale, "synthetic_project"),
        "No Project": _text(locale, "no_project_badge"),
    }[data_source]
    st.markdown(
        f"<div class='project-mode-badge'>{html.escape(label)}</div>",
        unsafe_allow_html=True,
    )


def _render_assistant_panel(
    locale: str,
    dataset: BuildingDataset | None,
    planner,
) -> None:
    history = st.session_state.get("chat_history", [])
    if history:
        st.markdown(
            f"<div class='assistant-title'>{html.escape(_text(locale, 'assistant_title'))}</div>",
            unsafe_allow_html=True,
        )
    with st.container(key="chat_history"):
        if not history:
            description = html.escape(_text(locale, "empty_description")).replace(
                "\n", "<br>"
            )
            st.markdown(
                "<div class='chat-empty'>"
                f"<div class='chat-empty-title'>{html.escape(_text(locale, 'empty_title'))}</div>"
                f"<div class='chat-empty-copy'>{description}</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        for item in history:
            _render_chat_turn(item, locale)

    enabled = dataset is not None and planner is not None
    with st.form("question_form", clear_on_submit=True, border=False):
        input_column, button_column = st.columns(
            [12, 1],
            gap=None,
            vertical_alignment="center",
        )
        with input_column:
            question = st.text_input(
                _text(locale, "question_placeholder"),
                placeholder=_text(locale, "question_placeholder"),
                disabled=not enabled,
                label_visibility="collapsed",
            )
        with button_column:
            submitted = st.form_submit_button(
                _text(locale, "send"),
                disabled=not enabled,
                width="stretch",
            )

    if submitted and dataset is not None and planner is not None:
        _submit_question(locale, dataset, planner, question)
        st.rerun()


def _submit_question(locale: str, dataset: BuildingDataset, planner, question: str) -> None:
    try:
        context = st.session_state.get("conversation_context")
        outcome = run_question(
            dataset,
            question,
            planner,
            context=context if isinstance(context, ConversationContext) else None,
        )
    except ResolutionError as error:
        error_key = _error_message_key(error.code)
        message = _guided_resolution_message(locale, error, dataset)
        _record_error(question, message, str(error))
        st.session_state["chat_history"][-1]["error_key"] = error_key
        payload = error.as_dict()
        payload["user_message"] = message
        rows = []
        for candidate in error.candidates:
            for entity in dataset.entities:
                if entity.entity_id == candidate:
                    rows.append({"Name": entity.name, "GlobalId": entity.global_id, "IFC": _ifc_type_label(entity.kind)})
                for prop in entity.properties:
                    if candidate == f"{prop.path} [#{prop.source_id}]":
                        rows.append({"Name": entity.name, "GlobalId": entity.global_id, "IFC": _ifc_type_label(entity.kind), "Source": prop.source.value, "Set": prop.set_name, "Field": prop.path, "Value": str(prop.value), "Unit": prop.unit})
        payload["evidence_rows"] = rows
        st.session_state["last_resolution_error"] = payload
    except (UnsupportedQueryError, InvalidPlannerOutputError) as error:
        message = _guided_unsupported_message(locale, dataset)
        _record_error(
            question,
            message,
            str(error),
        )
        st.session_state["chat_history"][-1]["error_key"] = "unsupported_query"
        st.session_state["last_resolution_error"] = (
            error.as_dict() if isinstance(error, UnsupportedQueryError) else
            {"code": "unsupported", "message": str(error), "candidates": []}
        )
    except LLMProviderError as error:
        _record_error(
            question,
            _text(locale, "llm_request_failed"),
            str(error),
        )
    except IncompleteDataError as error:
        _record_error(
            question,
            _guided_incomplete_data_message(locale, error),
            str(error),
        )
    except QueryExecutionError as error:
        _record_error(question, _text(locale, "unsupported_query"), str(error))
        st.session_state["chat_history"][-1]["error_key"] = "unsupported_query"
    else:
        st.session_state.pop("last_resolution_error", None)
        st.session_state["last_outcome"] = outcome
        st.session_state["conversation_context"] = ConversationContext.from_outcome(outcome)
        st.session_state.pop("last_error_details", None)
        st.session_state["chat_history"].append(
            {
                "question": question,
                "answer": AnswerBuilder().build(outcome.plan, outcome.result, locale).text,
                "outcome": outcome,
                "status": "answer",
            }
        )


def _record_error(question: str, message: str, details: str) -> None:
    st.session_state.pop("last_resolution_error", None)
    st.session_state.pop("last_outcome", None)
    st.session_state["last_error_details"] = details
    st.session_state["chat_history"].append(
        {
            "question": question,
            "answer": message,
            "status": "error",
        }
    )


def _error_message_key(code: str) -> str:
    if code == "unsupported":
        return "unsupported_query"
    return code if code in UI_TEXT["zh"] else "unsupported_query"


def _guided_resolution_message(
    locale: str,
    error: ResolutionError,
    dataset: BuildingDataset,
) -> str:
    if error.code == "missing_storey_data":
        return _text(locale, "missing_storey_data")
    if error.code == "entity_not_found":
        reference = _quoted_value(str(error))
        if locale == "zh":
            return (
                f"未找到“{reference}”。请检查构件编号，或改用完整名称、GlobalId 再试。"
                if reference else "没有找到对应的 BIM 对象。请检查构件编号、名称或 GlobalId。"
            )
        return (
            f"No BIM object matches “{reference}”. Check its element number, full name, or GlobalId."
            if reference else "No matching BIM object was found. Check its element number, name, or GlobalId."
        )
    if error.code == "missing":
        property_name, entity_name = _missing_property_details(str(error))
        suggestions = _available_property_names(dataset, entity_name)
        if locale == "zh":
            message = f"已找到“{entity_name}”，但 IFC 中没有可验证的“{property_name}”字段。"
            return message + (f" 可继续查询：{suggestions}。" if suggestions else "")
        message = f"“{entity_name}” was found, but its IFC data has no verifiable “{property_name}” field."
        return message + (f" Try: {suggestions}." if suggestions else "")
    if error.code == "ambiguous":
        count = len(error.candidates)
        if locale == "zh":
            return f"找到 {count} 个可能匹配的对象或字段，无法唯一确定。请从 IFC 证据面板选择具体候选。"
        return f"Found {count} possible objects or fields, so the answer is not unique. Choose a candidate in IFC Evidence."
    if error.code == "needs_context":
        if "count" in str(error).casefold() or "统计" in str(error):
            return "请说明要统计门、窗、梁、柱或其他构件。" if locale == "zh" else "Specify whether to count doors, windows, beams, columns, or another entity type."
        return "上一轮没有唯一对象，“它”无法对应到具体构件。请提供构件编号或名称。" if locale == "zh" else "The previous answer did not identify one object, so “it” is ambiguous. Provide an element number or name."
    if error.code == "understood_but_unavailable":
        return _guided_unsupported_message(locale, dataset, understood=True)
    return _text(locale, _error_message_key(error.code))


def _guided_unsupported_message(
    locale: str,
    dataset: BuildingDataset,
    *,
    understood: bool = False,
) -> str:
    kinds = _available_kind_names(dataset, locale)
    if locale == "zh":
        prefix = "已理解这个问题，但当前 IFC 没有对应的可验证数据。" if understood else "当前原型暂不支持这种查询。"
        return f"{prefix} 当前模型可查询：{kinds}。可改问构件数量、指定构件、尺寸或已有属性。"
    prefix = "The question is understood, but this IFC has no verifiable data for it." if understood else "This query is outside the current prototype scope."
    return f"{prefix} This model can query: {kinds}. Try an entity count, a named object, a dimension, or an available property."


def _guided_incomplete_data_message(locale: str, error: IncompleteDataError) -> str:
    if locale == "zh":
        return (
            f"已理解该问题，但“{error.field}”仅在 {error.available_count}/{error.total_count} 个"
            f"{_ifc_type_label(error.target_kind)} 中存在，无法给出可验证的完整答案。"
        )
    return (
        f"The question is understood, but “{error.field}” is available for only "
        f"{error.available_count}/{error.total_count} {error.target_kind} entities, so no complete verified answer is available."
    )


def _quoted_value(message: str) -> str | None:
    match = re.search(r"'([^']+)'", message)
    return match.group(1) if match else None


def _missing_property_details(message: str) -> tuple[str, str]:
    match = re.search(r"Property '([^']+)' is unavailable on '([^']+)'", message)
    return match.groups() if match else ("requested property", "this object")


def _available_property_names(dataset: BuildingDataset, entity_name: str) -> str:
    entity = next((item for item in dataset.entities if item.name == entity_name), None)
    if entity is None:
        return ""
    names = list(entity.attributes)
    names.extend(property.field_name for property in entity.properties)
    return "、".join(dict.fromkeys(names) if names else ())


def _available_kind_names(dataset: BuildingDataset, locale: str) -> str:
    labels = {
        "beam": ("梁", "beams"), "column": ("柱", "columns"),
        "slab": ("楼板", "slabs"), "footing": ("基础", "footings"),
        "pile": ("桩", "piles"), "door": ("门", "doors"),
        "window": ("窗", "windows"), "wall": ("墙", "walls"),
        "space": ("房间", "spaces"), "storey": ("楼层", "storeys"),
    }
    ordered = ("door", "window", "beam", "column", "wall", "slab", "footing", "pile", "space", "storey")
    names = [labels[kind][0 if locale == "zh" else 1] for kind in ordered if any(entity.kind == kind for entity in dataset.entities)]
    return "、".join(names) if locale == "zh" else ", ".join(names)


def _render_chat_turn(item: dict, locale: str) -> None:
    question = html.escape(item["question"])
    if outcome := item.get("outcome"):
        text = AnswerBuilder().build(outcome.plan, outcome.result, locale).text
    else:
        text = item["answer"]
        for key in ("unsupported_query", "incomplete_data", "llm_request_failed"):
            if text in (UI_TEXT["zh"][key], UI_TEXT["en"][key]):
                text = _text(locale, key)
                break
    answer = html.escape(text)
    status_class = " chat-message--error" if item["status"] == "error" else ""
    st.markdown(
        "<div class='chat-turn'>"
        f"<div class='chat-message chat-message--user'>{question}</div>"
        f"<div class='chat-message chat-message--assistant{status_class}'>{answer}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_evidence_panel(
    locale: str,
    drawings: tuple[DrawingDocument, ...],
) -> None:
    tabs = st.tabs(
        (
            _text(locale, "ifc_evidence"),
            _text(locale, "drawing_evidence"),
        ) + ((_text(locale, "query_details"),) if st.session_state.get("development_mode", False) else ()),
        default=_text(locale, "drawing_evidence") if getattr(st.session_state.get("drawing_retrieval"), "best", None) else _text(locale, "ifc_evidence"),
        key=f"evidence_tabs_{len(st.session_state.get('chat_history', []))}",
    )
    outcome = st.session_state.get("last_outcome")
    with tabs[0]:
        _render_ifc_evidence(locale, outcome)
    with tabs[1]:
        _render_drawing_panel(locale, drawings)
    if st.session_state.get("development_mode", False):
        with tabs[2]:
            _render_query_panel(locale, outcome)


def _render_ifc_evidence(
    locale: str,
    outcome: object,
) -> None:
    with st.container(key="ifc_evidence_scroll"):
        if not isinstance(outcome, ApplicationQueryResult) or not outcome.answer.evidence:
            if error := st.session_state.get("last_resolution_error"):
                st.error(error.get("user_message", _text(locale, _error_message_key(error["code"]))))
                if error["candidates"]:
                    if error.get("evidence_rows"):
                        labels = {"Name": "名称", "Source": "证据来源", "Set": "属性 / 工程量集", "Field": "字段", "Value": "数值", "Unit": "单位"} if locale == "zh" else {}
                        st.dataframe([{labels.get(k, k): v for k, v in row.items()} for row in error["evidence_rows"]], hide_index=True)
                    else:
                        st.dataframe([{_text(locale, "candidate"): candidate.split(" [#", 1)[0]} for candidate in error["candidates"]], hide_index=True)
                if st.session_state.get("development_mode", False):
                    st.json(error)
            _empty_state(_text(locale, "no_ifc_evidence"))
            return
        evidence_rows = []
        for evidence in outcome.answer.evidence:
            name = html.escape(evidence.name or _text(locale, "unnamed"))
            kind = html.escape(_ifc_type_label(evidence.kind))
            global_id = (
                html.escape(evidence.global_id)
                if evidence.global_id is not None
                else html.escape(_text(locale, "global_id_unavailable"))
            )
            evidence_rows.append(
                "<div class='evidence-row'>"
                "<div class='evidence-row-heading'>"
                f"<strong>{name}</strong><span>{kind}</span>"
                "</div>"
                f"<code>GlobalId: {global_id}</code>"
                "</div>"
            )
        count_label = _text(locale, "entity_count").format(
            count=len(outcome.answer.evidence)
        )
        st.markdown(
            "<div class='evidence-list-heading'>"
            f"<strong>{html.escape(_text(locale, 'ifc_evidence'))}</strong>"
            f"<span>{html.escape(count_label)}</span>"
            "</div>"
            f"<div class='evidence-list'>{''.join(evidence_rows)}</div>",
            unsafe_allow_html=True,
        )

        for evidence in outcome.answer.evidence:
            if evidence.properties:
                st.dataframe([
                    {
                        _text(locale, "source"): ({"IFC Attribute": "IFC 属性", "Property Set": "属性集", "Quantity Set": "工程量集", "Relationship-derived value": "关系派生值"}.get(p.source.value, p.source.value) if locale == "zh" else p.source.value),
                        _text(locale, "set"): p.set_name,
                        _text(locale, "field"): p.path,
                        _text(locale, "value"): str(p.value),
                        _text(locale, "unit"): p.unit or _text(locale, "unit_unavailable"),
                        **({"Measure Type": p.measure_type, "Unit Source": p.unit_source, "IFC Field ID": p.source_id, "Inherited": p.inherited} if st.session_state.get("development_mode", False) else {}),
                    }
                    for p in evidence.properties
                ], hide_index=True)


def _drawing_term_label(locale: str, source: str, text: str) -> str:
    labels = {
        "object name": "对象名称", "exported element number": "导出对象编号",
        "instance mark": "对象 Mark", "type mark (shared)": "共享 Type Mark",
        "storey label": "楼层名称", "spatial scope": "空间范围",
        "property-based Reference Level": "属性 Reference Level",
    }
    return f"{labels.get(source, source) if locale == 'zh' else source}: {text}"


def _render_drawing_panel(
    locale: str,
    drawings: tuple[DrawingDocument, ...],
) -> None:
    with st.container(key="drawing_evidence_scroll"):
        outcome = st.session_state.get("last_outcome")
        statistical = isinstance(outcome, ApplicationQueryResult) and (
            outcome.plan.operation in (QueryOperation.COUNT, QueryOperation.FILTER, QueryOperation.AGGREGATE)
            or len(outcome.result.entities) != 1
        )
        if statistical:
            st.caption(_text(locale, "statistical_drawing_note"))
        if not drawings:
            _empty_state(_text(locale, "no_drawing_evidence"))
            return

        retrieval = st.session_state.get("drawing_retrieval")
        best = retrieval.best if retrieval else None
        if best and statistical:
            with st.expander(_text(locale, "drawing_examples"), expanded=False):
                st.caption(_text(locale, "drawing_example_note"))
                st.caption(f"{best.drawing_number or best.document} · {_text(locale, 'page')} {best.page_number}")
                matched_document = next(d for d in drawings if d.file_name == best.document)
                _render_drawing_page(locale, matched_document, best.page_number)
        elif best:
            st.caption(_text(locale, "related_drawing"))
            st.caption(f"{_text(locale, 'drawing')}：{best.drawing_number or best.document} · {_text(locale, 'page')} {best.page_number}")
            st.caption(f"{_text(locale, 'match_basis')}：" + "; ".join(_drawing_term_label(locale, t.source, t.text) for t in best.matched_terms[:3]))
            st.caption(_text(locale, "ifc_answer_source"))
            matched_document = next(d for d in drawings if d.file_name == best.document)
            _render_drawing_page(locale, matched_document, best.page_number)
        elif st.session_state.get("chat_history"):
            st.caption(_text(locale, "no_reliable_drawing"))
            if isinstance(st.session_state.get("last_outcome"), ApplicationQueryResult):
                st.caption(_text(locale, "ifc_answer_source"))
        if retrieval and (not statistical or st.session_state.get("development_mode", False)):
            with st.expander(_text(locale, "match_details"), expanded=False):
                if st.session_state.get("development_mode", False):
                    st.json([asdict(c) for c in retrieval.candidates[:5]])
                else:
                    for candidate in retrieval.candidates[:5]:
                        st.caption(f"{candidate.drawing_number or candidate.document} · {_text(locale, 'page')} {candidate.page_number}")
                        st.text("; ".join(_drawing_term_label(locale, t.source, t.text) for t in candidate.matched_terms))
        with st.expander(_text(locale, "manual_drawings"), expanded=False):
            st.caption(_text(locale, "manual_note"))
            _render_manual_drawings(locale, drawings, best)


def _render_manual_drawings(locale: str, drawings: tuple[DrawingDocument, ...], best) -> None:
    drawing_by_name = {drawing.file_name: drawing for drawing in drawings}
    outcome = st.session_state.get("last_outcome")
    selection_key = (st.session_state.get("active_project_key"), getattr(outcome, "question", None), len(st.session_state.get("chat_history", [])))
    if st.session_state.get("_automatic_drawing_selection") != selection_key:
        st.session_state["_automatic_drawing_selection"] = selection_key
        if best:
            st.session_state["drawing_selector"] = best.document
            st.session_state["drawing_page_selector"] = best.page_number
    if st.session_state.get("drawing_selector") not in drawing_by_name:
        st.session_state.pop("drawing_selector", None)
    selected_name = st.selectbox(
        _text(locale, "drawing"),
        tuple(drawing_by_name),
        key="drawing_selector",
        label_visibility="collapsed",
    )
    selected_drawing = drawing_by_name[selected_name]
    if st.session_state.get("drawing_page_selector", 1) > selected_drawing.page_count:
        st.session_state.pop("drawing_page_selector", None)
    page_number = st.selectbox(
        _text(locale, "page"),
        tuple(range(1, selected_drawing.page_count + 1)),
        key="drawing_page_selector",
        format_func=lambda value: f"{_text(locale, 'page')} {value}",
    )
    _render_drawing_page(locale, selected_drawing, page_number)

    text_key = (
        "text_layer_available"
        if selected_drawing.has_text_layer
        else "text_layer_unavailable"
    )
    _status(
        f"{_text(locale, 'pages')}: {selected_drawing.page_count} · "
        f"{_text(locale, text_key)}",
        "success" if selected_drawing.has_text_layer else "neutral",
    )
    if not selected_drawing.has_text_layer:
        _status(_text(locale, "no_text_layer"), "neutral")

    query_term = st.text_input(
        _text(locale, "search_drawing"),
        placeholder=_text(locale, "search_placeholder"),
        key="drawing_text_search",
    )
    if query_term.strip():
        matches = [
            (drawing.file_name, page.page_number)
            for drawing in drawings
            for page in search_drawing_text(drawing, query_term)
        ]
        if matches:
            rows = "".join(
                "<div class='search-result'>"
                f"<span>{html.escape(file_name)}</span>"
                f"<strong>{html.escape(_text(locale, 'page'))} {matching_page}</strong>"
                "</div>"
                for file_name, matching_page in matches
            )
            st.markdown(
                f"<div class='evidence-label'>{html.escape(_text(locale, 'matching_pages'))}</div>{rows}",
                unsafe_allow_html=True,
            )
        else:
            _empty_state(_text(locale, "no_matching_pages"))


def _render_drawing_page(locale: str, selected_drawing: DrawingDocument, page_number: int) -> None:
    try:
        preview = PyMuPDFParser().render_page(selected_drawing, page_number)
    except PDFParseError as error:
        _status(
            f"{_text(locale, 'drawing_preview_failed')}: {error}",
            "warning",
        )
    else:
        st.image(
            "data:image/png;base64," + base64.b64encode(preview).decode("ascii"),
            caption=f"{selected_drawing.file_name} · {_text(locale, 'page')} {page_number}",
            width="stretch",
        )


def _render_query_panel(locale: str, outcome: object) -> None:
    with st.container(key="query_evidence_scroll"):
        if not isinstance(outcome, ApplicationQueryResult):
            details = st.session_state.get("last_error_details")
            if details:
                with st.expander(_text(locale, "developer_error")):
                    st.code(str(details))
            else:
                _empty_state(_text(locale, "no_query_details"))
            return

        with st.expander(_text(locale, "query_plan"), expanded=False):
            st.json(_plan_payload(outcome.plan))
        with st.expander(_text(locale, "query_result"), expanded=False):
            st.json(
                {
                    "operation": outcome.result.operation.value,
                    "value": outcome.result.value,
                    "entity_ids": [
                        entity.entity_id for entity in outcome.result.entities
                    ],
                }
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


def _entity_counts(dataset: BuildingDataset) -> dict[str, int]:
    return {
        kind: sum(entity.kind == kind for entity in dataset.entities)
        for kind in ("storey", "space", "door", "window", "wall")
    }


def _ifc_warnings(dataset: BuildingDataset, locale: str = "en") -> tuple[str, ...]:
    warnings = []
    kind_labels = {
        "storey": _text(locale, "storeys"),
        "space": _text(locale, "spaces"),
        "door": _text(locale, "doors"),
        "window": _text(locale, "windows"),
        "wall": _text(locale, "walls"),
    }
    for kind, label in kind_labels.items():
        missing_names = sum(
            entity.kind == kind and entity.name is None
            for entity in dataset.entities
        )
        if missing_names:
            warnings.append(
                _text(
                    locale,
                    "missing_name_one" if missing_names == 1 else "missing_name_many",
                ).format(
                    count=missing_names,
                    kind=_counted_kind(locale, kind, missing_names, label),
                )
            )
        if kind == "storey":
            continue
        missing_containers = sum(
            entity.kind == kind and entity.container_id is None
            for entity in dataset.entities
        )
        if missing_containers:
            warnings.append(
                _text(
                    locale,
                    "missing_container_one"
                    if missing_containers == 1
                    else "missing_container_many",
                ).format(
                    count=missing_containers,
                    kind=_counted_kind(locale, kind, missing_containers, label),
                )
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


def _planner(mode: str, locale: str = "en"):
    if mode == "development":
        if st.session_state.get("development_mode", False):
            _status(_text(locale, "development_planner_note"), "neutral")
        return DevelopmentNaturalLanguagePlanner()

    if not os.getenv("BIM_QA_LLM_API_KEY"):
        _status(_text(locale, "llm_key_missing"), "neutral")
        return None
    try:
        settings = LLMProviderSettings.from_environment()
    except MissingLLMConfigurationError as error:
        _status(
            f"{_text(locale, 'llm_config_incomplete')} {error}",
            "neutral",
        )
        return None
    return LLMQueryPlanner(OpenAICompatibleChatProvider(settings))


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
        "requested_property": plan.requested_property,
    }


def _status(message: str, kind: str) -> None:
    st.markdown(
        f"<div class='status status--{kind}'>{html.escape(message)}</div>",
        unsafe_allow_html=True,
    )


def _empty_state(message: str) -> None:
    st.markdown(
        f"<div class='empty-state'>{html.escape(message)}</div>",
        unsafe_allow_html=True,
    )


def _ifc_type_label(kind: str) -> str:
    return {
        "storey": "IfcBuildingStorey",
        "space": "IfcSpace",
        "door": "IfcDoor",
        "window": "IfcWindow",
        "wall": "IfcWall",
        "beam": "IfcBeam",
        "column": "IfcColumn",
        "slab": "IfcSlab",
        "footing": "IfcFooting",
        "pile": "IfcPile",
    }.get(kind, kind)


def _counted_kind(locale: str, kind: str, count: int, fallback: str) -> str:
    if locale == "zh":
        return fallback
    singular = {
        "storey": "storey",
        "space": "space",
        "door": "door",
        "window": "window",
        "wall": "wall",
    }.get(kind, kind)
    return singular if count == 1 else f"{singular}s"


def _text(locale: str, key: str) -> str:
    return UI_TEXT[locale][key]


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _inject_styles(locale: str) -> None:
    choose_file = html.escape(_text(locale, "choose_file"), quote=True)
    section_transform = "uppercase" if locale == "en" else "none"
    section_spacing = "0.06em" if locale == "en" else "0"
    st.markdown(
        f"""
        <style>
        :root {{
            --app-bg: #F4F7FB;
            --panel-bg: #FFFFFF;
            --text: #172033;
            --muted: #667085;
            --border: #E5EAF0;
            --cyan-soft: #CAEBED;
            --green-soft: #CCE7D9;
            --accent: #63BAD9;
            --accent-hover: #B5DAE9;
        }}

        html, body, .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {{
            height: 100vh !important;
            max-height: 100vh !important;
            overflow: hidden !important;
            background: var(--app-bg) !important;
            color: var(--text);
        }}

        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        footer {{
            display: none !important;
        }}

        [data-testid="stMainBlockContainer"] {{
            box-sizing: border-box;
            height: 100vh !important;
            max-width: none !important;
            padding: 8px 16px 12px !important;
            overflow: hidden !important;
        }}

        .stApp, .stApp * {{
            font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont,
                "Segoe UI", "Microsoft YaHei", sans-serif;
        }}

        .st-key-app_header {{
            height: 54px;
            min-height: 54px;
            margin-bottom: 8px;
        }}

        .st-key-app_header [data-testid="stHorizontalBlock"] {{
            height: 54px;
            align-items: center;
        }}

        .product-lockup {{ line-height: 1.05; }}
        .product-title {{
            color: var(--text);
            font-size: 20px;
            font-weight: 700;
            letter-spacing: -0.02em;
        }}
        .product-version {{
            color: var(--muted);
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0;
            vertical-align: middle;
        }}
        .product-subtitle {{
            color: var(--muted);
            font-size: 12px;
            font-weight: 500;
            margin-top: 5px;
        }}
        .header-status {{
            align-items: center;
            color: var(--muted);
            display: flex;
            font-size: 12px;
            font-weight: 600;
            gap: 7px;
            justify-content: flex-end;
            white-space: nowrap;
        }}
        .header-status span {{
            background: var(--accent);
            border-radius: 50%;
            display: inline-block;
            height: 7px;
            width: 7px;
        }}
        .st-key-app_header [data-testid="stButtonGroup"] {{
            display: flex;
            justify-content: flex-end;
        }}
        .st-key-app_header [data-testid="stButtonGroup"] button {{
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
            min-height: 28px !important;
            padding: 3px 10px !important;
        }}
        .st-key-app_header [data-testid="stButtonGroup"] button + button {{
            border-left: 1px solid var(--border) !important;
        }}
        .st-key-app_header button[data-variant="segmented_control"] {{
            color: var(--muted) !important;
        }}
        .st-key-app_header button[data-variant="segmented_control"][data-selected="true"] {{
            background: transparent !important;
            color: var(--text) !important;
            font-weight: 650 !important;
        }}

        .st-key-workspace {{
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            box-sizing: border-box;
            height: calc(100vh - 114px) !important;
            max-height: calc(100vh - 114px) !important;
            overflow: hidden;
        }}
        .st-key-workspace > [data-testid="stHorizontalBlock"] {{
            gap: 0 !important;
            height: 100%;
        }}
        .st-key-workspace > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
            height: 100%;
            min-width: 0;
        }}
        .st-key-project_panel,
        .st-key-assistant_panel,
        .st-key-evidence_panel {{
            background: var(--panel-bg);
            box-sizing: border-box;
            height: calc(100vh - 116px) !important;
            min-height: calc(100vh - 116px) !important;
            max-height: calc(100vh - 116px) !important;
            overflow: hidden;
        }}
        .st-key-project_panel {{
            border-right: 1px solid var(--border);
            gap: 9px !important;
            padding: 20px 18px 14px;
        }}
        .st-key-assistant_panel {{ padding: 20px 24px 16px; }}
        .st-key-evidence_panel {{
            border-left: 1px solid var(--border);
            padding: 12px 18px 14px;
        }}

        .panel-title,
        .assistant-title {{
            color: var(--text);
            font-size: 17px;
            font-weight: 650;
            letter-spacing: -0.01em;
        }}
        .panel-title {{ margin-bottom: 12px; }}
        .assistant-title {{ font-size: 18px; margin-bottom: 14px; }}
        .section-label {{
            color: var(--muted);
            font-size: 11px;
            font-weight: 600;
            letter-spacing: {section_spacing};
            margin: 8px 0 4px;
            text-transform: {section_transform};
        }}

        [data-testid="stFileUploader"] {{ margin: 0 !important; }}
        [data-testid="stFileUploaderDropzone"] {{
            background: var(--panel-bg) !important;
            border: 1px solid var(--border) !important;
            border-radius: 8px !important;
            min-height: 40px !important;
            padding: 4px 7px !important;
        }}
        [data-testid="stFileUploaderDropzoneInstructions"] {{ display: none !important; }}
        [data-testid="stFileUploaderDropzone"]:not(:has([data-testid="stFileChip"])) button {{
            background: var(--panel-bg) !important;
            border: 0 !important;
            color: transparent !important;
            font-size: 0 !important;
            min-height: 28px !important;
            padding: 3px 8px !important;
        }}
        [data-testid="stFileUploaderDropzone"]:not(:has([data-testid="stFileChip"])) button::after {{
            color: var(--text);
            content: "{choose_file}";
            font-size: 12px;
            font-weight: 600;
        }}
        [data-testid="stFileUploaderDropzone"]:has([data-testid="stFileChip"]) {{
            border: 0 !important;
            border-bottom: 1px solid var(--border) !important;
            border-radius: 0 !important;
            min-height: 36px !important;
            padding: 0 !important;
        }}
        [data-testid="stFileUploaderDropzone"]:has([data-testid="stFileChip"])
        button[aria-label="Add files"] {{ display: none !important; }}
        [data-testid="stFileChip"] {{
            background: var(--panel-bg) !important;
            border-radius: 0 !important;
            padding-left: 0 !important;
        }}

        .file-row, .stat-row, .search-result {{
            align-items: center;
            display: flex;
            min-height: 26px;
        }}
        .stat-row {{ gap: 8px; }}
        .file-row span {{
            color: var(--text);
            font-size: 12px;
            max-width: 70%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .file-row small, .stat-row span {{ color: var(--muted); font-size: 12px; }}
        .stat-row strong {{ color: var(--text); font-size: 14px; font-weight: 650; }}
        .empty-inline {{ color: var(--muted); font-size: 11px; padding: 4px 0; }}

        .status {{
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            font-size: 11px;
            line-height: 1.35;
            margin: 4px 0;
            padding: 5px 8px;
        }}
        .status--success {{ background: var(--green-soft); }}
        .status--warning, .status--neutral {{ background: var(--cyan-soft); }}
        .project-mode-badge {{
            color: var(--muted);
            font-size: 11px;
            margin-top: 4px;
        }}

        .st-key-project_panel [data-testid="stExpander"] {{
            background: var(--panel-bg);
            border: 0;
            border-radius: 0;
            border-top: 1px solid var(--border);
            margin-top: 10px;
        }}
        .st-key-project_panel [data-testid="stExpander"] details {{
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
        }}
        .st-key-project_panel [data-testid="stExpander"] summary {{
            color: var(--muted);
            font-size: 12px;
            justify-content: space-between;
            min-height: 38px;
            padding: 0 !important;
        }}
        .st-key-project_panel [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {{
            display: none !important;
        }}
        .st-key-project_panel [data-testid="stExpander"] summary::after {{
            color: var(--muted);
            content: "+";
            font-size: 16px;
            font-weight: 400;
        }}
        .st-key-project_panel [data-testid="stExpander"] details[open] summary::after {{
            content: "−";
        }}

        .st-key-project_panel [data-testid="stCheckbox"] {{ margin-top: 4px; }}
        .st-key-project_panel [data-testid="stCheckbox"] label,
        .st-key-project_panel [data-testid="stSelectbox"] label {{
            color: var(--muted) !important;
            font-size: 11px !important;
        }}
        .st-key-project_panel [data-testid="stButtonGroup"] {{ margin-top: 1px; }}
        .st-key-project_panel [data-testid="stButtonGroup"] button {{
            min-height: 28px !important;
            padding: 2px 6px !important;
        }}
        .st-key-project_panel button[data-variant="segmented_control"] {{
            border-color: var(--border) !important;
            color: var(--muted) !important;
            font-size: 10px !important;
        }}
        .st-key-project_panel button[data-variant="segmented_control"][data-selected="true"] {{
            background: var(--cyan-soft) !important;
            border-color: var(--accent) !important;
            color: var(--text) !important;
        }}
        .st-key-project_panel [data-testid="stSelectbox"] {{ margin-top: -5px; }}
        .st-key-project_panel [data-baseweb="select"] > div,
        .st-key-evidence_panel [data-baseweb="select"] > div {{
            background: var(--app-bg) !important;
            border-color: var(--border) !important;
            min-height: 34px !important;
        }}
        .st-key-evidence_panel .react-aria-ComboBox [role="group"] {{
            background: var(--panel-bg) !important;
            border: 1px solid var(--border) !important;
            border-radius: 8px;
        }}
        .st-key-evidence_panel .react-aria-ComboBox input {{
            background: transparent !important;
            color: var(--text) !important;
            font-size: 12px;
        }}

        .st-key-chat_history {{
            height: calc(100vh - 264px) !important;
            min-height: calc(100vh - 264px) !important;
            max-height: calc(100vh - 264px) !important;
            overflow-y: auto !important;
            padding: 6px 7px 12px 2px;
            scrollbar-color: #B5DAE9 transparent;
            scrollbar-width: thin;
        }}
        .st-key-chat_history:has(.chat-empty) > [data-testid="stElementContainer"],
        .st-key-chat_history:has(.chat-empty) [data-testid="stMarkdown"],
        .st-key-chat_history:has(.chat-empty) [data-testid="stMarkdown"] > div,
        .st-key-chat_history:has(.chat-empty) [data-testid="stMarkdownContainer"] {{
            height: 100%;
        }}
        .chat-empty {{
            align-items: center;
            display: flex;
            flex-direction: column;
            height: 100%;
            justify-content: center;
            text-align: center;
        }}
        .chat-empty-title {{
            color: var(--text);
            font-size: 18px;
            font-weight: 650;
            letter-spacing: -0.01em;
            margin-bottom: 10px;
        }}
        .chat-empty-copy {{
            color: var(--muted);
            font-size: 13px;
            line-height: 1.65;
        }}
        .empty-state {{
            color: var(--muted);
            font-size: 12px;
            padding: 28px 4px;
            text-align: center;
        }}
        .chat-turn {{ margin-bottom: 17px; }}
        .chat-message {{
            color: var(--text);
            font-size: 14px;
            line-height: 1.55;
            max-width: 75%;
        }}
        .chat-message--user {{
            background: var(--cyan-soft);
            border-radius: 12px;
            margin-left: auto;
            padding: 10px 14px;
        }}
        .chat-message--assistant {{
            margin-right: auto;
            margin-top: 10px;
            padding: 4px 2px;
        }}
        .chat-message--error {{
            background: var(--app-bg);
            border-left: 3px solid var(--accent);
            padding: 8px 10px;
        }}

        .st-key-assistant_panel [data-testid="stForm"] {{
            background: var(--panel-bg);
            border: 1px solid var(--border) !important;
            border-radius: 14px;
            margin-top: 2px;
            min-height: 52px;
            padding: 5px 5px 5px 12px;
        }}
        .st-key-assistant_panel [data-testid="stForm"]:has(input:focus) {{
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 1px var(--accent);
        }}
        .st-key-assistant_panel [data-testid="stForm"] [data-testid="stHorizontalBlock"] {{
            gap: 0 !important;
        }}
        .st-key-assistant_panel [data-testid="stTextInput"] [data-baseweb="input"] {{
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }}
        .st-key-assistant_panel [data-testid="stTextInputRootElement"] {{
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }}
        .st-key-assistant_panel [data-testid="stTextInput"] input,
        .st-key-evidence_panel [data-testid="stTextInput"] input {{
            color: var(--text) !important;
            min-height: 40px !important;
        }}
        .st-key-assistant_panel [data-testid="stTextInput"] input {{
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }}
        .st-key-evidence_panel [data-testid="stTextInputRootElement"] {{
            background: var(--panel-bg) !important;
            border: 1px solid var(--border) !important;
            border-radius: 8px !important;
        }}
        .st-key-evidence_panel [data-testid="stTextInput"] input:focus {{
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 1px var(--accent) !important;
        }}
        .st-key-assistant_panel [data-testid="stFormSubmitButton"] button {{
            background: var(--accent) !important;
            border: 0 !important;
            border-radius: 10px !important;
            color: transparent !important;
            font-size: 0 !important;
            height: 40px;
            min-height: 40px;
            min-width: 40px;
            padding: 0 !important;
        }}
        .st-key-assistant_panel [data-testid="stFormSubmitButton"] button::after {{
            color: var(--text);
            content: "→";
            font-size: 21px;
            font-weight: 500;
        }}
        .st-key-assistant_panel [data-testid="stFormSubmitButton"] button:hover {{
            background: var(--accent-hover) !important;
        }}

        .st-key-evidence_panel [data-testid="stTabs"] {{ height: 100%; }}
        .st-key-evidence_panel [data-baseweb="tab-list"] {{
            border-bottom: 1px solid var(--border);
            gap: 10px;
        }}
        .st-key-evidence_panel [data-baseweb="tab"] {{
            background: transparent !important;
            border-radius: 0 !important;
            color: var(--muted);
            font-size: 13px;
            padding: 9px 4px 10px;
        }}
        .st-key-evidence_panel [aria-selected="true"] {{
            color: var(--text) !important;
            font-weight: 650;
        }}
        .st-key-evidence_panel .react-aria-SelectionIndicator {{
            background: var(--accent) !important;
        }}
        .st-key-ifc_evidence_scroll,
        .st-key-drawing_evidence_scroll,
        .st-key-query_evidence_scroll {{
            height: calc(100vh - 184px) !important;
            min-height: calc(100vh - 184px) !important;
            max-height: calc(100vh - 184px) !important;
            overflow-y: auto !important;
            padding: 10px 3px 12px 1px;
            scrollbar-color: #B5DAE9 transparent;
            scrollbar-width: thin;
        }}

        .evidence-list-heading {{
            align-items: center;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            padding: 4px 0 12px;
        }}
        .evidence-list-heading strong {{
            color: var(--text);
            font-size: 14px;
            font-weight: 650;
        }}
        .evidence-list-heading span {{ color: var(--muted); font-size: 11px; }}
        .evidence-row {{
            border-bottom: 1px solid var(--border);
            padding: 13px 0 12px;
        }}
        .evidence-row-heading {{
            align-items: baseline;
            display: flex;
            gap: 10px;
            justify-content: space-between;
        }}
        .evidence-row-heading strong {{
            color: var(--text);
            font-size: 13px;
            font-weight: 650;
        }}
        .evidence-row-heading span {{ color: var(--muted); font-size: 11px; }}
        .evidence-row code {{
            background: transparent;
            color: var(--muted);
            display: block;
            font-family: "SFMono-Regular", Consolas, monospace;
            font-size: 11px;
            margin-top: 5px;
            overflow: hidden;
            padding: 0;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .evidence-label {{
            color: var(--muted);
            font-size: 11px;
            font-weight: 600;
            letter-spacing: {section_spacing};
            margin: 9px 0 3px;
            text-transform: {section_transform};
        }}
        .search-result {{
            color: var(--text);
            font-size: 11px;
            justify-content: space-between;
            padding: 5px 0;
        }}
        .search-result span {{
            max-width: 72%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .st-key-evidence_panel [data-testid="stExpander"] {{
            background: var(--panel-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            margin-bottom: 8px;
        }}
        .st-key-evidence_panel [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {{
            display: none !important;
        }}
        .st-key-evidence_panel [data-testid="stImage"] img {{
            border: 1px solid var(--border);
            border-radius: 6px;
            max-height: 360px;
            object-fit: contain;
        }}
        div[data-testid="stMarkdownContainer"] p {{ margin-bottom: 0; }}

        @media (max-width: 1100px) {{
            [data-testid="stMainBlockContainer"] {{
                padding-left: 10px !important;
                padding-right: 10px !important;
            }}
            .header-badges span:last-child {{ display: none; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
