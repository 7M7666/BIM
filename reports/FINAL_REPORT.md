# BIM Evidence QA — Phase 4 + Phase 5 Final Report

日期：2026-09-11。项目：`W:/LiWanlin/workplace/python/bim`。

本次按 Phase 4 ground truth → evaluation → 保存 BIM-only baseline → Phase 5 retrieval → drawing evaluation → 浏览器验收与最终回归的顺序执行。没有制作幻灯片，没有执行额外 future work。

## A. 项目最终能力

- 上传真实 IFC4 和带文本层 PDF，保留 Project / BIM Assistant / Drawing Evidence 三栏工作区。
- 支持 beam、column、slab、footing、pile、door、window、wall、space、storey 的受控查询。支持 count、list/find，以及已有的受控 aggregate 操作；本次课程集未评测所有 aggregate 表达。
- 中文、英文和混合输入进入同一 canonical QueryPlan；可按精确 Name、GlobalId、导出的元素编号查找对象。
- RAC 的楼层查询使用真实 IfcBuildingStorey containment；RST 使用 `Constraints.Reference Level`，答案明确区分 property-based level 与空间包含关系。
- 单对象 Property / Quantity 查询、有限 scalar properties 展示；本地 resolver 执行真实字段检查、缺失和歧义规则。数值来自 IFC，不由 LLM 生成。
- 结构化 GlobalId 和字段 Evidence，包括来源、Set、Field、Value、measure type、unit、source ID、unit source；单位来源沿用 Phase 3 的 IFC 元数据规则。
- 结构化 success、missing、ambiguous、unsupported、entity_not_found 状态。
- 从 IFC 证据生成 PDF 检索词，确定性排序候选页并自动选中最佳 PDF/页；保留匹配原因、分数、标题、图号、其他候选。无可靠匹配或最高分并列时不强选。

## B. Phase 4 BIM-only baseline

[冻结 baseline](W:/LiWanlin/workplace/python/bim/reports/bim_only_baseline.json) 实际在 Phase 5 修改前生成，文件时间为 2026-09-11 21:17:58（本地时间）。SHA256：

`9420fdc68b971c5bd2c601f7075d48acf855e4015dc649b30498c822dd301590`

48 个课程案例：RAC 22，RST 26；英文 29，中文 9，中英混合 10。非纯英文占 19/48。类别为 count 13、list 5、find 3、spatial scope 3、Reference Level 3、property 12、missing 2、ambiguous 1、unsupported 5、entity_not_found 1。

Ground truth 通过原始 ifcopenshell 实体、关系和 Quantity 读取建立，不调用 QA planner、engine 或 property resolver来生成期望值。每例保留 IFC 哈希、对象 ID/GlobalId、预期计划字段、来源与核验说明。独立 raw-IFC 核验测试确认 frozen JSON 未变。图纸标签由页面文字及相关渲染图核对；没有声称获得外部人员的人工签字复核。

## C. Phase 5 final metrics

以下均使用 **DevelopmentNaturalLanguagePlanner**。没有调用真实 LLM API，不能视为 LLM 准确率或对未知项目的泛化评估。

| 指标 | Phase 4 BIM-only | Phase 5 final |
|---|---:|---:|
| Planning / Understanding | 48/48，100% | 48/48，100% |
| Answer | 48/48，100% | 48/48，100% |
| IFC Evidence | 39/39，100% | 39/39，100% |
| Status / Refusal | 48/48，100% | 48/48，100% |
| Fully correct | 48/48，100% | 48/48，100% |
| Cases with any scored failure | 0 | 0 |
| Drawing Top-1（可定位子集） | 未执行 | 10/10，100% |
| Drawing coverage（可定位子集） | 未执行 | 10/10，100% |
| 无匹配对照，单独报告 | 未执行 | 2/2 正确 abstention |

[Phase 5 结果](W:/LiWanlin/workplace/python/bim/reports/phase5_final.json) 与 baseline 的全部 48 个 BIM `results` 逐项相同，未引入 BIM 回归。

计分规则：每个指标使用预先确定的 applicable denominator。Planning、Answer、Status 对全部 48 例计分，正确拒答也是正确答案。Evidence 对全部 39 个预期成功案例计分，即使规划或执行提前失败也不会缩小分母。规划比较 operation、entity type、requested property、scope 和目标对象集合；答案比较状态、对象集合和实际数值，浮点 tolerance 为 rel=1e-8、abs=1e-6；Evidence 比较 GlobalId、字段路径/来源/measure type/unit。Fully correct 要求所有适用 BIM 检查及已标注的正例 drawing 检查通过。负向 drawing controls 单独计分，不抬高 Top-1。

## D. Error Analysis

[首次评测记录](W:/LiWanlin/workplace/python/bim/reports/course_initial.json) 原样保留：44/48 fully correct，4 个失败案例。首轮 Planning 45/48，Answer 45/48，Evidence 37/39，Status 47/48。

| 案例 | 期望与实际差异 | 原因和处理 |
|---|---|---|
| course-19，Find 精确 Door Name | 对象正确，但 plan.kind 为空 | 补回精确名称对应的 canonical kind |
| course-20，Find beam 1046268 | 应为指定 beam，误匹配短空间名 `1` | 名称子串匹配没有词边界；增加边界并复用本地精确对象 resolver |
| course-21，Find Column GlobalId | 应找到柱，实际 unsupported | list/find 分支未支持对象 ID；增加通用 GlobalId/元素编号解析 |
| course-42，明确对象的 Area | 系统正确返回 ambiguous，但评分不通过 | 实际候选附带 `[#IFC行号]`；评分器在比较路径时剥离该展示后缀，未改 ground truth |

初始错误类别计数允许一例多类：planner_entity_error 3、answer_error 3、evidence_error 2、object_resolution_error 2、planner_operation_error 1、property_resolution_error 1、scope_resolution_error 1。部分为上游失败引起的下游检查失败，不应当当作互相独立的 bug 数。

最终失败案例列表为空，各错误类别计数为 0。missing_data、ambiguity_handling_error、unsupported_handling_error、unit_error 同样受结构化检查覆盖。正确的 missing/ambiguous 不记为系统错误：missing 2/2，ambiguous 1/1，unsupported 5/5，entity_not_found 1/1。

另有两个开发验证问题已修复：新测试初次误将 fixture 的 `(raw IFC, dataset)` 元组传给 evaluator，调整为 dataset 后通过；实际浏览器发现热重载后临时预览媒体 URL 返回 404，改为内联已渲染 PNG 后，浏览器确认 `complete=true`、`naturalWidth=3572`，图片正常显示。早期诊断截图仍保留，演示应使用标注为 final 的截图。

## E. Drawing Retrieval

输入只取结构化 IFC 对象与 scope，不把完整用户问题交给 PDF 搜索。使用精确对象名、带标识上下文的导出元素编号、独立行 Mark、重复 Type Mark、楼层标签。数字匹配具有边界；`103` 不匹配 `A103`、`1103` 或 `103.5`，裸尺寸数字不当作元素编号。

排序可解释：对象全名权重 14，导出元素编号 12，实例标记 8，共享类型标记 4，scope 3，storey label 2；Plan sheet 提供 2 分上下文，最低候选分数 5。标记只用于有可靠 Plans 标题的页面；短类型标记还须在独立行重复出现。并列最高分保留候选但不自动选页。标题/图号从真实 Revit titleblock 文字位置提取，无法确认时留空，不按页码猜。

结构：`document, page_number, sheet_title, drawing_number, matched_terms, score, reason`。每个 term 还保留 source、weight、相关 entity_ids。检索结果不修改 BIM answer。

成功示例：

- RAC Door 422466：IFC Mark=103 → A102 Plans，第 3 页。
- RAC Window 457479：Type Mark=46 → A102，第 3 页；这是共享类型关联，不能声称精确定位了该窗。
- RST Reference Level=Level 2 → S101 Framing Plans，第 2 页；仅为相关楼层图纸，不证明 84 根梁的个体位置或 storey containment。
- RST Footing 1178029 → S204 Footing Detail，第 6 页；文本明确出现 `Continuous footing (1178029)`。
- RST 导出 IfcPile 1175183 → S203 Central Pile Section，第 5 页；明确出现 `Pile cap (1175183)`。

不能定位的实例：梁 1046268、柱 1046264。PDF 只出现共享型号 `200UB25.4`，没有足以唯一关联对象的编号；均返回 `No reliable drawing evidence found.`。这两个对照没有计入正例 Top-1。

图纸标注共 12 例：10 个可定位正例，2 个无匹配对照。只有 10/48 的 BIM 案例获得了正向页面标签；其余未标注案例不计算 drawing accuracy。100% coverage 特指 10 个正例，绝不表示所有 BIM 问题都有可靠图纸证据。

## F. 实际浏览器 / Streamlit Demo

通过 agent-browser 操作真实 Chromium 浏览器，访问本地 Streamlit，并用真实文件上传控件上传 IFC/PDF；没有用 AppTest 注入数据替代此验收。UI 使用中文，Development Planner，最终截图视口 1600×1000。

RAC 顺序：上传 `rac_basic_sample_project.ifc` 和同名 PDF → 打开开发设置 → 选择开发规划器。

1. `有多少扇门？` → 16，自动选 A102 / 第 3 页。
2. `Level 2 有多少门？` → 10，明确 Spatial containment / IfcBuildingStorey Level 2。
3. `Single-Flush:800 x 2100:422466 的宽度是多少？` → 800.0 mm；IFC tab 显示 GlobalId `1PDnLIM013wvkZO9Lb4$s7`、Quantity Set、Qto_DoorBaseQuantities、Width。
4. `Single-Flush:800 x 2100:422466 这个门的面积是多少？` → ambiguous，列出 Dimensions.Area 与 Qto_DoorBaseQuantities.Area。
5. 修复预览后重新执行门宽问题，PNG 实际解码且第 3 页显示正常。

RST 顺序：移除 RAC 上传文件，再上传 `rst_basic_sample_project.ifc` 和同名 PDF。

1. `有多少根梁？` → 370。
2. `Reference Level 为 Level 2 的梁有多少？` → 84，答案明确 `This is not IfcBuildingStorey containment.`，自动 S101 / 第 2 页。
3. `梁 1046268 的长度是多少？` → 4242.6 mm；GlobalId `3zL2DJMkrEuekgiISjJ_Rg`、Qto_BeamBaseQuantities.Length、Quantity Set 一致。Drawing tab 明确无可靠匹配。
4. `What is the width of footing 1178029?` → 原始浮点值 900.0000000000001 mm（约 900 mm），自动 S204 / 第 6 页，PNG 解码正常。

证据文件：

- [RAC 最终 Answer + PDF](W:/LiWanlin/workplace/python/bim/reports/demo/rac-width-final.png)
- [RAC IFC 字段](W:/LiWanlin/workplace/python/bim/reports/demo/rac-width-ifc.png)
- [RAC ambiguity](W:/LiWanlin/workplace/python/bim/reports/demo/rac-ambiguous.png)
- [RST Beam Answer + IFC](W:/LiWanlin/workplace/python/bim/reports/demo/rst-beam-ifc.png)
- [RST Reference Level](W:/LiWanlin/workplace/python/bim/reports/demo/rst-reference-level.png)
- [RST Footing 图纸](W:/LiWanlin/workplace/python/bim/reports/demo/rst-footing.png)

同目录保存对应 `.txt` 浏览器 accessibility snapshots；这些截图是实际浏览器验收记录，不是完整演示录像。

## G. Tests

最终结果以 [pytest 日志](W:/LiWanlin/workplace/python/bim/reports/pytest-final.txt) 为准。

| original | new | total passed | failed | skipped | xfailed |
|---:|---:|---:|---:|---:|---:|
| 264 | 89 | 353 | 0 | 0 | 0 |

新增 Phase 4 测试 61 项；Phase 5 测试 28 项。包括 48 个逐例 canonical/result 检查、raw IFC ground truth 再核验、错误计划/对象/scope/数值/单位/证据的变异检查、提前失败不缩分母、12 个真实 drawing cases、数字边界、排序、并列拒绝、共享类型、标题提取、无页面匹配计分、UI 自动选页与手动切页。原 synthetic evaluation 文件与既有 tests 保留。`git diff --check` 通过。

## H. 本阶段修改文件

| 文件（项目内相对路径） | 本次作用 |
|---|---|
| src/bim_evidence_qa/evaluation/schema.py | 在既有 EvaluationCase 上增加可选课程期望字段，保留 legacy schema |
| src/bim_evidence_qa/evaluation/runner.py | 给原 Runner 增加 course 入口，synthetic run 不变 |
| src/bim_evidence_qa/evaluation/course.py | 完整计划/答案/状态/Evidence 评分，失败记录、固定分母、drawing 评分与结果保存 |
| src/bim_evidence_qa/evaluation/course_ground_truth.py | 原始 IFC ground truth author/verifier；默认只验证冻结文件 |
| src/bim_evidence_qa/query/planner.py | 修复名称边界、补全实体类型、复用对象 resolver 支持 find ID |
| src/bim_evidence_qa/parsers/pdf.py | 最小扩展 DrawingPage 标题/图号，沿用文本解析与渲染 |
| src/bim_evidence_qa/drawing.py | IFC 证据词、可解释排序、结构化候选与无可靠匹配处理 |
| src/bim_evidence_qa/web.py | 自动 PDF/页/tab 选择、简短匹配说明、候选详情、内联预览、无关联的手动预览提示；更新开发规划器语言说明 |
| tests/fixtures/course_cases.json | 冻结 48 个真实 BIM 案例 |
| tests/fixtures/course_drawing_cases.json | 冻结 10 个图纸正例与 2 个无匹配对照及逐例依据 |
| tests/test_course_evaluation.py | 61 项真实 benchmark/评分器测试 |
| tests/test_drawing_retrieval.py | 28 项 retrieval/真实 PDF/UI 回归测试 |
| reports/course_initial.json | 原始失败结果，保留不覆盖 |
| reports/bim_only_baseline.json | Phase 4 强制检查点，Phase 5 后未改写 |
| reports/phase5_final.json | 最终逐例 BIM/drawing 结果、指标、错误记录、输入哈希 |
| reports/FINAL_REPORT.md、presentation_notes.md | 本报告及可用于后续演示的已核实内容 |
| reports/demo/*、pytest-final.txt、diff-check.txt、verification.json | 浏览器/图纸核验记录、回归日志和 baseline 比较记录 |

Git 中还存在此前 Phase 2/3 的未提交修改；它们属于既有工作，不在上表冒充本阶段新增。没有提交 commit 或发布。

## I. 当前已知限制

- 48 例属于开发中检查并修复过的课程回归集，没有独立 held-out 集；100% 不等于任意自然语言问题都能正确回答。
- 实际 LLM 的理解率、稳定性、时延和成本未评测；本轮统计与浏览器均为 Development Planner。
- 中文支持是受控 normalization，不是翻译系统；复杂句式、多对象推理和无明确对象的“这个/它”可能 unsupported。
- Drawing evidence 是候选相关页；Type Mark 和楼层只能关联类型/视图，不能证明对象坐标、空间位置或 IFC 数值。PDF 与 IFC 来自同一 Revit 源也不保证 PDF 写出每个对象编号。
- 标题提取适用于当前可识别的 Revit 文本排列，其他模板可能没有标题；没有 OCR/CV/几何注册。
- 多份上传 PDF 未建立通用的模型版本/文档身份验证机制；用户需上传正确配套图纸。跨项目重复 Mark 存在风险，并列得分会拒绝自动定位。
- 保留原始浮点值可能出现显示尾数，例如 900.0000000000001；未改变数据或伪造精度。
- IFC 字段表较宽，部分列需横向滚动；本轮只做 Evidence 必需调整，没有 UI 重设计。
- 没有材料系统扩展、成本模型、几何推断、RVT parser、conversation memory 扩展。

## J. 课程要求逐项对照

| 要求 | 状态 | 已验证范围 |
|---|---|---|
| Working Demo | Complete | 实际浏览器 RAC/RST 上传及问答验收 |
| PDF upload | Complete | RAC 6 页、RST 14 页，文本解析和预览 |
| IFC upload | Complete | 老师两份 IFC4 模型 |
| Natural-language QA | Complete | 当前受控 query 类型；不等于开放式任意推理 |
| deterministic BIM grounding | Complete | 属性值与统计来自本地 IFC 查询 |
| GlobalId Evidence | Complete | 集合及单对象字段证据，课程集逐例核验 |
| Ground Truth Evaluation | Complete | 48 个冻结真实案例，完整字段与固定分母 |
| Error Analysis | Complete | 首轮失败保留，最终逐例失败列表与分类 |
| Drawing Evidence | Complete | 文本候选页检索、排序、自动预览、10 正例与 2 对照评测；不包括几何定位 |
| Chinese / English query support | Complete | 中文/英文/混合 canonical normalization 与真实查询验证 |

在上述明确范围内，项目功能性交付已达到所列课程要求。15 分钟、5–10 页的最终汇报与团队成员/角色页尚未制作；按本次要求只保存 verified presentation notes，不声称完成整场课堂展示或最终评分。
