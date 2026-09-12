# BIM Evidence QA

BIM Evidence QA 是一个用于课堂演示的 Streamlit 应用。它回答上传 IFC 模型中的受限自然语言问题，并在有可靠匹配时提供配套 PDF 图纸页。每个答案先转换为受验证的 `QueryPlan`，再由本地 IFC 数据确定性执行；数值、属性、单位、实体 ID 和 GlobalId 均来自 IFC，而非模型生成。

在线演示：[bimworkingdemo.streamlit.app](https://bimworkingdemo.streamlit.app/)

当前界面版本：`v0.1.0`

## 项目能力

- 解析 IFC4 为本地规范化数据集，保留实体、属性集、工程量、单位、GlobalId 和来源信息。
- 支持中文、英文和中英混合的受控提问，覆盖楼层、房间、门、窗、墙、梁、柱、楼板、基础和桩。
- 支持 count、list/find、精确对象解析、IfcBuildingStorey 空间包含、基于属性的 `Reference Level`、单对象 Property/Quantity、已支持的 aggregate、结构化拒答和项目概览 `overview`。
- `overview` 由“当前建筑/模型/项目”或隐含当前模型的构件概览语义识别，不按完整句子匹配。`这个建筑有什么？`、`这个模型包含什么？`、`有哪些构件？`、`give me an overview of this model` 都会生成同一个 canonical `overview` plan。
- 概览统计直接读取当前解析 IFC 数据，只返回数量大于 0 的已支持类别及真实数量。没有 `IfcBuildingStorey` 的模型不会被虚构楼层数量。
- “有几层楼”“有多少楼层”“how many storeys”等问题只按 `IfcBuildingStorey` 计数；若模型没有该实体，应用明确说明无法从空间层级确定楼层数，不会按 `Reference Level` 数量推断。
- 成功答案提供确定性 IFC 证据。可选 LLM Planner 只能提出计划，计划仍在本地校验；LLM 不直接生成 BIM 事实。
- 图纸检索从结构化 IFC 证据生成检索词。可靠对象级匹配可作为图纸证据；count、list、filter、aggregate 和 overview 回答均明确为 IFC 模型统计，不会由单页 PDF 冒充直接证明。

## 问答流程

```mermaid
flowchart LR
    Q[中文 / 英文问题] --> N[术语归一化]
    N --> P[受验证的 QueryPlan]
    P --> E[确定性 IFC 查询引擎]
    E --> A[答案与 IFC 证据]
    A --> R[基于 IFC 证据的可选 PDF 检索]
```

确定性查询引擎是答案数值的唯一来源。PDF 检索只在存在可靠对象级关联时提供页面级支持，不能证明全模型的数量或聚合结果。

## 本地运行

要求：Python 3.11+ 与 IFC 文件。PDF 可选，但图纸检索需要与模型配套的 PDF。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
streamlit run app.py
```

打开 Streamlit 输出的地址，上传 IFC，并可选上传配套 PDF。普通课堂界面只显示项目、BIM 问答、IFC 证据和图纸证据；内部开发设置仅通过 `?dev=1` 进入。

### 可选 LLM Planner 配置

离线的 `DevelopmentNaturalLanguagePlanner` 覆盖当前受控查询边界。真实 LLM Planner 仅在已有环境变量都配置时可用；仓库不保存 API Key。

```powershell
$env:BIM_QA_LLM_API_KEY = "..."
$env:BIM_QA_LLM_ENDPOINT = "https://.../chat/completions"
$env:BIM_QA_LLM_MODEL = "..."
```

未配置时，UI 会说明状态；内部开发模式仍可使用 Development Planner。

## 示例问题

| 意图 | 中文 | 英文 |
| --- | --- | --- |
| 项目概览 | `这个建筑有什么？` | `What does this building contain?` |
| 数量 | `有多少扇门？` | `How many windows are there?` |
| 精确查找 | `查找 Door 422466` | `Find beam 1046268` |
| 属性 | `梁 1046268 的长度是多少？` | `What is the width of footing 1178029?` |
| 范围计数 | `Level 2 有多少门？` | `How many beams have Reference Level Level 2?` |
| 楼层缺失状态 | `有几层楼？` | `How many storeys are there?` |

系统会拒绝当前边界以外的问题，例如几何推理、任意多跳关系、施工时序、成本与图纸视觉理解。

## 评测结果

课程回归与外部 held-out 评测必须分开理解。

| 评测 | 范围 | 结果 |
| --- | --- | --- |
| 课程回归集 | 48 个 RAC/RST 开发案例 | planning、answer、status 均为 48/48；适用 IFC 证据为 39/39。 |
| 课程图纸标注 | 10 个可定位正例与 2 个无匹配对照 | 标注正例 Top-1 与 coverage 为 10/10；正确 abstention 为 2/2。 |
| IFC-Bench V2 held-out | 5 个未见项目、7 个 IFC、271 个官方问题，seed `20260912` | 16/271 预分类为 supported（5.90% coverage）；9 个自动评分 supported 题为 0/9，原因是全部在执行前的规划阶段失败。 |

48 个课程案例是开发回归集，不能视为独立泛化基准。IFC-Bench 结果即使较低也被完整保留：16 个 supported case 暴露了 Planner 的措辞与模型 schema 限制。冻结的 external run 未运行真实 LLM Planner，因为 `BIM_QA_LLM_*` 凭据不可用；IFC-Bench 没有与课程等价的配套 PDF，因此不评价 Drawing Retrieval。

详细记录：

- [课程最终报告](reports/FINAL_REPORT.md)
- [外部验证报告](reports/external_validation/EXTERNAL_VALIDATION_REPORT.md)
- [9 个自动评分与 7 个 manual-review 案例人工审计](reports/external_validation/MANUAL_AUDIT.md)

## 测试

完整测试在本地课程 IFC 文件可用时使用该目录；这些课程文件不会提交。

```powershell
$env:BIM_QA_COURSE_DATA = (Resolve-Path 2026)
python -m pytest -q
git diff --check
```

回归覆盖多种中英文 overview 表达、RAC/RST 的真实实体统计、RST 不伪造楼层、缺失 `IfcBuildingStorey` 时的明确中文数据状态，以及既有 count 查询不被 overview 捕获。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `app.py` | Streamlit 入口 |
| `src/bim_evidence_qa/` | 领域模型、IFC/PDF 解析、Planner、查询引擎、答案、图纸检索和 UI |
| `tests/` | 单元、应用、课程回归、图纸与部署检查 |
| `reports/` | 冻结的课程与外部验证报告及结果 |

## 当前边界

该项目是受限的、面向证据的 BIM QA 课堂演示。它不实现 OCR、计算机视觉、IFC 几何到图纸坐标注册、通用视觉问答或为提高 benchmark 分数而进行的 Planner 适配。图纸证据是课程配套 PDF 的页面级检索辅助，不应被解释为完整的图纸理解系统。
