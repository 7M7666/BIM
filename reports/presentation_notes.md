# 可用于后续 5–10 页、15 分钟（含 Q&A）汇报的已核实材料

尚未制作幻灯片。团队姓名、分工与发言顺序未提供，不能代填。下面是可复用的内容，不是已完成的演示录像。

**Motivation / capability**：把建筑自然语言问题转成受控查询，数值由 IFC 确定性执行给出，并保留 GlobalId、Qto/Pset 字段、单位与相关 PDF 页供核验。

**Compact metrics**（Development Planner；课程回归集，不是未知问题泛化率）：

| 指标 | BIM-only | Final |
|---|---:|---:|
| Planning / Answer / Status | 各 48/48 | 各 48/48 |
| IFC Evidence | 39/39 | 39/39 |
| Fully correct | 48/48 | 48/48 |
| Drawing Top-1 / coverage | — | 各 10/10（可定位子集） |
| 无匹配对照 | — | 2/2，单独计分 |
| pytest | 原 264 | 353 passed，0 failed/skipped/xfailed |

**三个代表性成功问答**：

1. `有多少扇门？` → RAC 16；相关图纸 A102 第 3 页。
2. `Reference Level 为 Level 2 的梁有多少？` → RST 84；明确 property-based level，不能伪装为 IfcBuildingStorey containment。
3. `梁 1046268 的长度是多少？` → 4242.6 mm，GlobalId `3zL2DJMkrEuekgiISjJ_Rg`，Qto_BeamBaseQuantities.Length。

**两个代表性错误/拒答案例**：

- 首轮 `Find beam 1046268` 被短名称 `1` 子串误匹配；通过名称边界与精确对象 resolver 修复。首轮全部失败记录仍在 course_initial.json。
- 明确 Door 422466 的通用 Area → ambiguous：Dimensions.Area 约 2.965 与 Qto Area 约 1.68；正确行为是列出候选，不能静默选择。

**RAC Demo 顺序**：上传 RAC IFC/PDF → 选择 Development Planner → 门数量 16 → Level 2 门数量 10 → Door 422466 宽度 800 mm → IFC tab 看 GlobalId/字段 → Drawing tab 看自动第 3 页 → 通用 Area 展示 ambiguity。可使用 reports/demo/rac-width-final.png 和 rac-ambiguous.png。

**RST Demo 顺序**：切换到 RST IFC/PDF → 梁数量 370 → Reference Level 2 为 84 → Beam 1046268 Length 为 4242.6 mm → IFC tab 核对证据 → Drawing tab 明确无可靠实例匹配 → 可补充 Footing 1178029，展示自动 S204 第 6 页。可使用 rst-beam-ifc.png、rst-reference-level.png、rst-footing.png。

**Lessons learned**：IFC containment 和 Reference Level 不是同一种关系；同一语义字段可能存在不同来源和值；数字 Mark 不能使用普通子串检索；需要实际浏览器验证图片解码，不能只验证页码和 AppTest；100% 必须同时说明分母、拒答规则和数据范围。

**当前限制**：开发规划器只支持受控语言；无真实 LLM 评测和 held-out 测试；共享窗型号只关联页面而非唯一窗；很多 RST 梁无可匹配 PDF 编号；无 OCR/CV/几何注册；PDF 标题提取有模板限制；用户需提供正确配套 PDF。

**Future steps（只保留供汇报，不执行）**：独立新问题/新模型评测；真实 LLM 规划器对照；更严格的文档版本与 Mark 关联；更广泛的 PDF 标题模板验证。优先提高可核验性，不以强行返回页码提高 coverage。

完整证据、测试命令、逐项课程要求和修改文件见 reports/FINAL_REPORT.md。
