# BIM Evidence QA

BIM Evidence QA is a Streamlit classroom demonstration for grounded questions about an uploaded IFC model and its paired drawing PDF. It converts a question into a validated `QueryPlan`, executes that plan against locally parsed IFC data, and presents IFC provenance alongside any reliable drawing-page retrieval result.

Live demo: [bimworkingdemo.streamlit.app](https://bimworkingdemo.streamlit.app/)

## What it does

- Parses IFC4 into a normalized local dataset; quantities, properties, units, entity IDs, and GlobalIds remain IFC-derived.
- Accepts controlled Chinese, English, and mixed-language questions for storeys, spaces, doors, windows, walls, beams, columns, slabs, footings, and piles.
- Supports count, list/find, exact object resolution, storey containment, property-based `Reference Level`, scalar property/quantity lookup, supported aggregates, structured refusals, and the project-level `overview` intent.
- Detects overview intent from a building/model/project target plus overview semantics, without matching complete sentences. Examples include `这个建筑有什么？`, `这个模型包含哪些构件？`, `给我概览一下这个项目。`, `What does this building contain?`, and `What kinds of elements are in this model?`.
- Computes overview counts from the parsed dataset only. It shows only supported entity categories with a count above zero; for example, an IFC model without `IfcBuildingStorey` does not receive an invented storey count.
- Returns deterministic IFC evidence for successful answers. An optional LLM planner may produce a plan, but it is validated locally and never produces BIM facts directly.
- Retrieves paired PDF pages from structured IFC evidence. Object-level matches may be shown as drawing evidence; count, list, aggregate, filter, and overview answers are clearly presented as IFC statistics rather than being attributed to one PDF page.

## How a question is answered

```mermaid
flowchart LR
    Q[Chinese / English question] --> N[Terminology normalization]
    N --> P[Validated QueryPlan]
    P --> E[Deterministic IFC query engine]
    E --> A[Answer and IFC evidence]
    A --> R[Optional PDF retrieval from IFC evidence]
```

The deterministic engine is the source of answer values. PDF retrieval can provide page-level supporting evidence when a reliable object-level link exists; it does not prove an aggregate statistic such as a model-wide count.

## Run locally

Requirements: Python 3.11+ and an IFC model. A paired PDF is optional but required for drawing retrieval.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
streamlit run app.py
```

Open the URL printed by Streamlit, upload an IFC file, and optionally upload its paired drawing PDF. The normal classroom interface exposes Project, BIM Assistant, IFC Evidence, and Drawing Evidence. Internal development controls are available only through `?dev=1`.

### Planner configuration

The deterministic `DevelopmentNaturalLanguagePlanner` works offline for the controlled query boundary. The optional real LLM planner requires all existing environment variables below; no key is stored in this repository.

```powershell
$env:BIM_QA_LLM_API_KEY = "..."
$env:BIM_QA_LLM_ENDPOINT = "https://.../chat/completions"
$env:BIM_QA_LLM_MODEL = "..."
```

The LLM planner can only return a locally validated plan. If the configuration is absent, the UI reports that state and the development planner remains available in internal development mode.

## Example questions

| Intent | Chinese | English |
| --- | --- | --- |
| Overview | `这个建筑有什么？` | `What does this building contain?` |
| Count | `有多少扇门？` | `How many windows are there?` |
| Find | `查找 Door 422466` | `Find beam 1046268` |
| Property | `梁 1046268 的长度是多少？` | `What is the width of footing 1178029?` |
| Scoped count | `Level 2 有多少门？` | `How many beams have Reference Level Level 2?` |

The planner intentionally refuses questions outside its controlled boundary, including geometry reasoning, arbitrary multi-hop relationships, construction sequencing, cost, and visual interpretation of drawings.

## Evaluation

Two result sets are deliberately separate.

| Evaluation | Scope | Result |
| --- | --- | --- |
| Course regression set | 48 RAC/RST development cases | 48/48 planning, answers, and status checks; 39/39 applicable IFC-evidence checks. |
| Course drawing labels | 10 positive page-level labels plus 2 no-match controls | 10/10 Top-1 and coverage on the labelled positive subset; 2/2 correct abstentions. |
| IFC-Bench V2 held-out run | 5 unseen projects, 7 IFC models, 271 official questions, seed `20260912` | 16/271 pre-classified supported (5.90% coverage); 0/9 automatic supported answers because all supported attempts failed before execution. |

The course set is a development regression set, not an independent generalization benchmark. The held-out IFC-Bench result is intentionally retained even though it is low: its 16 supported cases exposed Planner phrasing and model-schema limits. The frozen run did not evaluate a real LLM planner because `BIM_QA_LLM_*` credentials were unavailable, and it does not evaluate drawing retrieval because IFC-Bench has no paired course-equivalent PDFs.

Detailed records:

- [Course final report](reports/FINAL_REPORT.md)
- [External validation report](reports/external_validation/EXTERNAL_VALIDATION_REPORT.md)
- [Manual audit of the 9 automatic-score and 7 manual-review cases](reports/external_validation/MANUAL_AUDIT.md)

## Tests

The complete suite uses the local course IFC directory when available. It is intentionally not committed.

```powershell
$env:BIM_QA_COURSE_DATA = (Resolve-Path 2026)
python -m pytest -q
git diff --check
```

The latest local run completed with `393 passed`. The overview regressions cover multiple Chinese and English formulations, real RAC/RST entity counts, the absence of a synthetic RST storey count, and preservation of existing count planning.

## Repository layout

| Path | Purpose |
| --- | --- |
| `app.py` | Streamlit entry point |
| `src/bim_evidence_qa/` | Domain model, IFC/PDF parsers, planners, query engine, answers, drawing retrieval, and UI |
| `tests/` | Unit, application, course-regression, drawing, and deployment checks |
| `reports/` | Frozen course and external-validation reports/results |

## Current boundary

This project is a constrained, evidence-oriented BIM QA demonstration. It does not implement OCR, computer vision, geometry-to-drawing registration, generic visual question answering, or benchmark-driven planner adaptation. Drawing evidence remains a page-level retrieval aid for the course PDFs and must not be interpreted as a full drawing-understanding system.
