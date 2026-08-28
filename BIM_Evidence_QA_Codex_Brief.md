# BIM / Drawing Question-Answering Assistant 项目说明

## 1. 项目背景

课程要求小组完成一个 BIM 相关项目。我们小组共有 5 人。

当前计划选择：

**Track A — BIM / Drawing Question-Answering Assistant**

老师给出的核心要求包括：

- 做出一个可以实际运行的 Demo
- 界面需要支持上传建筑相关文件
- 主要数据包括建筑图纸和 IFC BIM 模型
- 用户能够针对建筑项目进行自然语言提问
- 回答不能只是大模型自由生成
- 回答需要基于真实 BIM / drawing 数据
- IFC 是重要的 evidence store
- 回答应能够引用相关 IFC 对象的 `GlobalId`
- 需要使用老师提供的数据作为 ground truth 做准确率评估
- 需要进行 error analysis
- 项目周期较短，所以范围不能无限扩大，但前端不能做成几个写死的问题按钮

---

## 2. 我们对 Track A 的理解

我们希望实现的不是：

- 固定问题查询器
- ChatPDF
- 单纯让 LLM 看 PDF 后回答
- 写死 5～10 个问题
- 只做 IFC 数据展示页面

而是：

> 一个支持上传建筑图纸和 IFC BIM 模型的自然语言建筑问答系统。系统自动解析用户上传的项目文件。用户可以自由输入自然语言问题，系统理解问题、生成查询计划，从 IFC 和图纸中寻找可验证的信息，最终返回答案、IFC GlobalId 和对应图纸证据。

核心原则：

**问题可以自由表达，但答案必须落在当前上传建筑项目中可验证的数据范围内。**

---

## 3. 最终用户流程

```text
上传建筑项目
      ↓
PDF Drawings + IFC
      ↓
系统自动解析
      ↓
建立项目数据索引
      ↓
用户自由输入自然语言问题
      ↓
LLM 理解问题并生成查询计划
      ↓
Query Engine 查询 IFC / Drawing Data
      ↓
得到结构化结果
      ↓
返回最终答案
      ↓
同时显示 IFC GlobalId + Drawing Evidence
```

---

## 4. 上传文件

第一阶段必须支持：

### 4.1 PDF 建筑图纸

例如：

- Floor Plan
- Elevation
- Section
- Door Schedule
- Window Schedule
- Room Schedule

支持：

```text
.pdf
```

### 4.2 IFC BIM 模型

支持：

```text
.ifc
```

IFC 主要用于：

- 获取真实建筑对象
- 查询构件属性
- 查询房间
- 查询楼层
- 查询门窗
- 查询面积等属性
- 获取对象关系
- 获取 `GlobalId`
- 作为回答的 evidence / ground truth

### 4.3 后续可选格式

只有核心功能稳定之后再考虑：

```text
.png
.jpg
.csv
.xlsx
```

不要第一阶段就追求所有格式。

---

## 5. 前端产品形态

不要只做聊天框。

建议做成一个完整的 Project Workspace。

### 5.1 上传页

```text
BIM Evidence QA

Upload your building project

[ Upload Drawing PDF ]
[ Upload IFC Model   ]

A101.pdf        ✓
A102.pdf        ✓
project.ifc     ✓

[ Process Project ]
```

---

### 5.2 项目解析状态

处理完成后显示：

```text
Project Ready

Drawings      12
Floors         3
Rooms         42
Doors         76
Windows       58
```

这些数字必须来自真实解析结果，而不是写死。

---

### 5.3 主问答界面

推荐三栏布局：

```text
┌──────────────┬──────────────────────┬──────────────────┐
│ Project      │ BIM Assistant        │ Drawing Evidence │
│              │                      │                  │
│ Files        │ Ask anything about   │ PDF Preview      │
│ A101.pdf ✓   │ this building        │                  │
│ A102.pdf ✓   │                      │ Current page     │
│ model.ifc ✓  │ > user question      │                  │
│              │                      │ Highlight area   │
│ Floors 3     │ Answer               │ if possible      │
│ Rooms 42     │                      │                  │
│ Doors 76     │ Evidence             │                  │
└──────────────┴──────────────────────┴──────────────────┘
```

---

## 6. 自然语言问答设计

前端不要限制用户只能选择固定问题。

用户应该可以输入：

```text
How many doors are on Level 1?
```

也可以输入：

```text
Count all the doors on the ground floor.
```

或者：

```text
What's the total number of doors downstairs?
```

系统应该能够理解它们属于相同或相近的查询。

---

## 7. 系统内部不要让 LLM 直接回答

不推荐：

```text
PDF / IFC
   ↓
LLM
   ↓
Answer
```

推荐：

```text
Natural Language Question
          ↓
     LLM Parser
          ↓
 Structured Query Plan
          ↓
      Query Engine
       ↙       ↘
     IFC      Drawing
       ↘       ↙
      Evidence
          ↓
 Answer Generator
          ↓
Answer + GlobalId + Drawing Evidence
```

LLM 的主要职责：

> 理解用户想查什么。

LLM 不应该直接决定建筑事实。

---

## 8. Structured Query Plan

例如用户问：

```text
Which rooms on Level 2 are larger than 20 square metres?
```

LLM 可以转换为：

```json
{
  "entity": "IfcSpace",
  "operation": "list",
  "filters": {
    "storey": "Level 2",
    "area": {
      "gt": 20
    }
  }
}
```

然后由 Python Query Engine 真正查询 IFC。

---

## 9. Query Engine 能力

不要把问题写死。

但可以在后台定义一组通用查询能力。

第一阶段建议支持：

```text
find
count
filter
compare
aggregate
relationship
locate
```

这些是能力，不是固定问题。

例如：

### find

```text
Where is Door D12?
```

### count

```text
How many doors are on Level 1?
```

### filter

```text
Show all rooms larger than 20 m².
```

### compare

```text
Which is larger, Room 201 or Room 205?
```

### aggregate

```text
Which room has the largest area?
```

### relationship

```text
Which doors belong to Room 101?
```

### locate

```text
Show Door D12 on the drawing.
```

这些能力可以组合。

例如：

```text
Which three rooms on Level 2 have the largest area, and how many doors does each room have?
```

如果能够支持这种组合查询，会明显提升项目质量。

---

## 10. IFC 数据解析

建议使用：

```text
IfcOpenShell
```

重点读取：

```text
IfcProject
IfcBuilding
IfcBuildingStorey
IfcSpace
IfcDoor
IfcWindow
IfcWall
```

以及：

- Name
- ObjectType
- Property Sets
- Quantities
- Area
- Dimensions
- Storey relationships
- Spatial containment
- Object relationships
- GlobalId

第一阶段不要解析所有 IFC 类型。

---

## 11. PDF 图纸解析

建议使用：

```text
PyMuPDF
```

第一阶段目标：

- 上传 PDF
- 获取页数
- 获取页面文本
- 获取 drawing / sheet 标题
- 建立 page index
- 根据回答找到可能相关页面
- 在界面中显示该页面

高分扩展：

- 对对应区域进行高亮
- 门窗标签定位
- Room 标签定位
- OCR / drawing symbol extraction

高亮如果困难，可以作为第二阶段功能，不要影响核心系统闭环。

---

## 12. 回答格式

最终回答不要只有一句自然语言。

建议统一输出：

```text
Answer

Room 205 has the largest area on Level 2.

Area
46.2 m²

IFC Evidence
Type: IfcSpace
GlobalId: 2xx...

Drawing Evidence
Sheet: A102
Page: 4

[ View on Drawing ]
```

如果一个回答涉及多个 IFC 对象，则展示多个 GlobalId。

---

## 13. Evidence Grounding

这是项目的重要设计点。

理想流程：

```text
Answer
  ↓
IFC Object
  ↓
GlobalId
  ↓
Drawing Page
```

系统需要尽可能回答：

1. 答案是什么
2. 数据来自哪个 IFC 对象
3. 对应的 GlobalId 是什么
4. 对应哪张图纸
5. 如果可能，图纸上的位置在哪里

---

## 14. 文件缺失情况

建议系统能处理不同上传组合。

### 只有 IFC

```text
IFC loaded
Drawing not uploaded

BIM queries are available.
Drawing evidence is unavailable.
```

### 只有 PDF

```text
Drawing loaded
IFC not uploaded

Drawing-based retrieval is available.
IFC-backed verification is unavailable.
```

### PDF + IFC

```text
Full Evidence Mode
```

但是课程最终 Demo 优先使用：

```text
PDF + IFC
```

---

## 15. Evaluation

不要只展示 Demo。

老师要求 measured accuracy against ground truth。

建议建立一个测试集。

重点是：

**测试问题应该是 unseen natural-language questions，而不是开发时写死的问题。**

例如总共准备 50～100 个问题。

可以覆盖：

```text
attribute retrieval
counting
filtering
relationship
aggregation
location
mixed / compositional query
```

---

## 16. 建议评估指标

### 16.1 Question Understanding Accuracy

系统是否正确理解用户意图。

例如：

```text
92%
```

### 16.2 Answer Accuracy

最终建筑事实是否正确。

例如：

```text
90%
```

### 16.3 Evidence Accuracy

GlobalId 是否对应正确对象。

例如：

```text
95%
```

### 16.4 Drawing Retrieval Accuracy

是否找到正确图纸页。

例如：

```text
88%
```

最后形成表格：

| Metric | Accuracy |
|---|---:|
| Question Understanding | xx% |
| Answer | xx% |
| IFC Evidence | xx% |
| Drawing Retrieval | xx% |

不要预设最终数字，必须真实测试后填写。

---

## 17. Error Analysis

项目必须保留失败案例。

例如：

```text
Question:
Which doors connect Room 101 and the corridor?

Expected:
D12, D13

System:
D12
```

然后分析：

```text
Failure Type:
Relationship Query

Possible Cause:
The IFC spatial relationship does not directly encode
the second-side room association.
```

建议最终把错误分成几类：

```text
Natural language misunderstanding
IFC data missing
IFC relationship ambiguity
Drawing retrieval error
Entity name mismatch
Complex compositional query failure
```

然后统计每种错误占比。

---

## 18. 推荐技术栈

第一版尽量简单：

```text
Python
Streamlit
IfcOpenShell
PyMuPDF
LLM API
```

### Streamlit

负责：

- Web UI
- 文件上传
- 状态展示
- 聊天输入
- 结果展示
- PDF Preview

### IfcOpenShell

负责：

- IFC parsing
- BIM object query
- Property extraction
- relationship extraction
- GlobalId

### PyMuPDF

负责：

- PDF parsing
- page text
- preview
- page retrieval

### LLM

负责：

- Natural language understanding
- Query planning
- Answer wording

不要让 LLM 直接充当建筑数据库。

---

## 19. 五人分工建议

### Member 1 — Frontend / UX

负责：

- Streamlit
- 上传文件
- 三栏界面
- Chat UI
- PDF preview
- Project dashboard

### Member 2 — IFC Parsing

负责：

- IfcOpenShell
- IFC entity extraction
- Property extraction
- GlobalId
- Storey / Space / Door / Window

### Member 3 — Drawing Processing

负责：

- PDF parser
- page index
- sheet identification
- drawing retrieval
- PDF evidence

### Member 4 — AI / Query Engine

负责：

- LLM question parser
- query schema
- query planner
- query execution interface
- compositional query

### Member 5 — Evaluation / Integration

负责：

- 模块整合
- test questions
- ground truth
- accuracy
- error analysis
- demo script
- report / slides

每个人不是完全隔离。

系统接口必须尽早统一。

---

## 20. 开发顺序

### Phase 1 — 最小闭环

先跑通：

```text
Upload IFC
   ↓
Parse IFC
   ↓
Ask:
"How many rooms are there?"
   ↓
Query IfcSpace
   ↓
Return correct answer
   ↓
Return GlobalId evidence
```

这一步完成之前不要大量做 UI。

---

### Phase 2 — PDF 接入

```text
Upload PDF
   ↓
Parse pages
   ↓
Build page index
   ↓
Question
   ↓
Return IFC answer
   ↓
Retrieve relevant drawing page
```

---

### Phase 3 — Natural Language Query Planning

实现：

```text
Question
↓
Structured Query Plan
↓
Query Engine
```

避免写死完整问题。

---

### Phase 4 — UI 完整化

完成：

- Upload page
- Project status
- Chat
- Evidence panel
- PDF preview
- loading / error state

---

### Phase 5 — Evaluation

建立 unseen test set。

统计：

- understanding accuracy
- answer accuracy
- evidence accuracy
- drawing retrieval accuracy

---

### Phase 6 — High-score Improvements

时间允许后再加入：

- drawing highlight
- compositional queries
- conversation context
- follow-up questions
- better relation queries
- visual query plan
- confidence score

---

## 21. 高分优先级

优先级从高到低：

### P0 必须完成

- PDF 上传
- IFC 上传
- IFC parsing
- 自然语言输入
- Query Engine
- 正确答案
- GlobalId evidence
- Working Demo

### P1 强烈建议

- Drawing retrieval
- PDF preview
- Project overview
- 多种自然语言表达
- Real evaluation
- Error analysis

### P2 加分项

- Drawing highlight
- Complex query
- Follow-up question
- Conversation context
- Confidence
- Query visualization
- Better UI

不要为了 P2 导致 P0 不稳定。

---

## 22. 不希望 Codex 做的事情

开发过程中请避免：

1. 不要把问题 hard-code 成固定问题列表
2. 不要写大量 if/elif 判断完整句子
3. 不要让 LLM 直接根据常识编建筑答案
4. 不要使用假数据填充最终 Demo
5. 不要提前写死 rooms / doors / floors 数量
6. 不要一开始支持过多 IFC 类型
7. 不要为了 UI 重构核心数据逻辑
8. 不要未经确认大量新增依赖
9. 不要一次性生成整个系统后声称完成
10. 不要隐藏失败案例

---

## 23. 对 Codex 的工作方式要求

开始开发前：

1. 先检查当前仓库结构
2. 说明现状
3. 给出最小可行架构
4. 明确模块之间的数据接口
5. 再开始写代码

每完成一个阶段：

1. 运行真实测试
2. 报告测试结果
3. 明确哪些功能是真的完成
4. 明确哪些只是 placeholder
5. 不要把未验证功能写成“已完成”

优先：

```text
small changes
testable changes
end-to-end first
```

不要：

```text
big rewrite
premature abstraction
over-engineering
```

---

## 24. 当前建议项目名

暂定：

**BIM Evidence QA**

副标题：

> Natural-language BIM & Drawing Question Answering with Verifiable IFC Evidence

项目名之后可以再调整。

---

## 25. 项目一句话定义

> Build a web-based BIM and drawing question-answering assistant that allows users to upload architectural PDF drawings and IFC models, ask free-form natural-language questions about the building, and receive answers grounded in real project data with verifiable IFC GlobalIds and corresponding drawing evidence.

---

## 26. 当前第一步

Codex 接手项目后，不要马上实现全部功能。

请先：

1. 检查项目目录
2. 检查 Python 环境和已有依赖
3. 检查老师提供的 IFC / PDF 文件
4. 使用 IfcOpenShell 对 IFC 做 exploratory parsing
5. 输出当前 IFC 中实际存在的：
   - storeys
   - spaces
   - doors
   - windows
   - property sets
   - quantities
   - GlobalIds
6. 判断哪些数据适合第一版 Query Engine
7. 给出 Phase 1 的最小实现计划
8. 等确认后再开始正式实现

目标是先理解真实数据，再设计系统，不根据想象写代码。
