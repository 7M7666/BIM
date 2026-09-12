# External Validation — IFC-Bench V2

This is a held-out generalization measurement, not a new training or development set. It uses IFC-Bench V2 from the official [dataset repository](https://huggingface.co/datasets/sylvainHellin/ifc-bench), revision `66c0737e7a48d7e0ce9303f213d88f670cb27855`. The official dataset and questions are CC BY 4.0; individual IFC model licences are recorded in [benchmark_manifest.json](benchmark_manifest.json). Model files are held only in an external local cache and are not committed.

## Frozen scope

- Seed: `20260912`.
- Unseen projects: `4351`, `ac20`, `fantasy_hotel_1`, `molio`, `wbdg_office`.
- IFC models: 7. All parsed successfully.
- Official questions retained: 271.
- Development work did not use these projects, models, questions, answers, or results. RAC/RST remain separate course-development regression data.

Selection, file hashes, model licences, protocol hashes, and the complete official-case manifest are saved in [selected_projects.json](selected_projects.json), [benchmark_manifest.json](benchmark_manifest.json), [protocol.json](protocol.json), and [external_cases.json](external_cases.json). The supported/unsupported classification was saved before system execution in [classification_protocol.json](classification_protocol.json).

## Capability coverage and Development Planner result

| Measure | Result |
| --- | ---: |
| External questions | 271 |
| Supported by frozen system boundary | 16 |
| Unsupported by frozen system boundary | 255 |
| Coverage | 5.90% |
| Scoreable supported questions | 9 |
| Correct supported answers | 0 |
| Supported accuracy | 0.00% |
| Manual-review-required supported questions | 7 |
| Overall end-to-end success lower bound | 0 / 271 (0.00%) |
| Correct data refusal | 0 / 1 |
| Parser/model-load failures | 0 / 7 |

Only the 16 pre-classified supported questions were sent to `DevelopmentNaturalLanguagePlanner` and the deterministic Engine. The 255 out-of-scope questions were deliberately not run, so correct refusal for them is **not measured**; it must not be interpreted as 255 correct refusals. The overall figure is therefore a lower bound over the full 271-question denominator, not an answer-quality score for unsupported questions.

All 16 supported attempts failed at planning. The primary recorded category is `planner_operation_error` (16): five width cases encountered the model-schema mismatch for the simplified aggregate `width` attribute; six extrema questions were not mapped to a supported aggregate plan; two extrema cases had no aggregate attribute; and three cases failed entity/subject resolution. See [development_planner_results.json](development_planner_results.json) and [failure_analysis.json](failure_analysis.json). No system changes were made in response.

The 255 unsupported questions are retained in the manifest. Their category-only counts are: grouped/compound aggregation 118; unsupported entities or systems 69; relation/collection 23; material system 20; geometry/spatial reasoning 15; project metadata 7; cost 2; construction sequencing 1.

## English / Chinese / mixed generalization

The scope-reduced language set has the frozen ten IDs `23, 24, 55, 61, 81, 618, 620, 622, 646, 971`, selected before language execution with the same seed. English is taken from the primary development result; Chinese and mixed variants are faithful frozen semantic translations.

| Language | Scoreable cases | Correct | Accuracy |
| --- | ---: | ---: | ---: |
| English | 5 | 0 | 0.00% |
| Chinese | 5 | 0 | 0.00% |
| Mixed | 5 | 0 | 0.00% |

Each language subset also has five manual-review-required cases. The detailed outcomes are in [chinese_results.json](chinese_results.json), [mixed_results.json](mixed_results.json), and [language_subset.json](language_subset.json). This comparison was observational only; no terminology rules were added after it.

## Real LLM Planner

Not run. `BIM_QA_LLM_API_KEY`, `BIM_QA_LLM_ENDPOINT`, and `BIM_QA_LLM_MODEL` were unavailable. No new provider, credentials, or external API was added.

## Boundary and limitations

This validates BIM-QA generalization only. IFC-Bench has no course-equivalent paired PDFs, so it does not evaluate Drawing Evidence. The existing course drawing result remains the separate 10 positive page-level labels plus 2 no-match controls. No OCR, CV, geometry registration, stability experiment, or benchmark-driven system modification was performed.
