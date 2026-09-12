# External Validation Manual Audit

## Scope and method

This audit manually reviews the nine automatic-score failures and seven `manual_review_required` cases in the frozen IFC-Bench V2 external-validation run (seed `20260912`). It reads the saved official question/answer, frozen capability classification, planner error, plan, and scoring fields in [development_planner_results.json](development_planner_results.json). No Planner, Engine, terminology, retrieval logic, scorer, or benchmark ground truth was changed.

## Direct findings

All 16 cases stopped during planning: every record has `plan: null`, `run_status: failed`, and no deterministic Engine answer. The numeric scorer is only invoked after successful execution, so none of the nine automatic cases reached `score_numeric`.

| Finding | Count | Interpretation |
| --- | ---: | --- |
| Automatic-score cases reviewed | 9 | All scored zero because planning failed before scoring. |
| Scorer or unit-comparison false negatives | 0 / 9 | No numeric value or actual unit existed to compare. |
| Manual-review cases reviewed | 7 | All were unscored because planning failed; manual status did not conceal a returned answer. |
| Cases classified too broadly for the current end-to-end Development Planner | 16 / 16 | The frozen `supported` label described conceptual Engine-level operations more broadly than the current planner can express against these models and phrasings. |
| Primary lexical/implicit-semantics Planner generalization failures | 9 / 16 | The planner did not map ordinary extrema wording to an aggregate plan. |
| Primary schema or support-boundary mismatches | 7 / 16 | Five generic-width aggregates, one empty entity set, and one missing-data refusal could not be planned under the current catalog constraints. |

The last two rows are root-cause categories, while the 16/16 classification finding is an end-to-end capability conclusion: a question can expose a Planner generalization gap and also show that the original support classification was too broad for the shipped system.

## Nine automatic-score cases

| ID | Question (abridged) | Official answer | What stopped | Audit conclusion |
| --- | --- | --- | --- | --- |
| 23 | Average door width | 0.99 m | `width` unavailable in model catalog | Schema/support-boundary mismatch; not scorer or unit failure. |
| 24 | Largest door width | 1.73 m | `width` unavailable in model catalog | Schema/support-boundary mismatch; not scorer or unit failure. |
| 58 | Narrowest door width | 1.0 m | Planner resolves “narrowest used here” as an entity | Lexical Planner generalization failure. |
| 61 | Narrowest window width | 0.9 m | Planner resolves “narrowest used” as an entity | Lexical Planner generalization failure. |
| 85 | Which beams are used? | No beam elements | `beam` absent from model entity catalog | Empty-set support boundary was classified too broadly; Planner rejected before an empty-result/refusal path. |
| 336 | Largest room | Area values unavailable/undefined | No aggregate attribute inferred | Missing-data refusal was classified too broadly; Planner never formed the prerequisite aggregate query. |
| 622 | Largest window width | 3.972 m | `width` unavailable in model catalog | Schema/support-boundary mismatch; not scorer or unit failure. |
| 970 | Average door width | 0.96 m | `width` unavailable in model catalog | Schema/support-boundary mismatch; not scorer or unit failure. |
| 971 | Largest door width | 1.83 m | `width` unavailable in model catalog | Schema/support-boundary mismatch; not scorer or unit failure. |

## Seven manual-review cases

| ID | Question (abridged) | Official answer identifies | Planner outcome | Audit conclusion |
| --- | --- | --- | --- | --- |
| 55 | Largest room | Room 006 / Seminarraum / 128.3 m² | Does not understand question | Lexical/implicit-area Planner generalization failure. |
| 60 | Widest window | IFC Fenster – ein Panel / 1.0 m | Does not understand question | Lexical Planner generalization failure. |
| 81 | Rooms with tallest ceilings | All rooms, 2.70 m | Does not understand question | Lexical Planner generalization failure. |
| 618 | Largest room | Rum nr. K13 (Gang) / 220.5 m² | Does not understand question | Lexical/implicit-area Planner generalization failure. |
| 620 | Widest door | Revolving Door 25 / 2.95529 m | Does not understand question | Lexical Planner generalization failure. |
| 646 | Rooms with tallest ceilings | Listed rooms and stored heights | Does not understand question | Lexical Planner generalization failure. |
| 952 | Largest room | Open Office (203) / 57.6 m² | No aggregate attribute inferred | Implicit-area Planner generalization failure. |

`manual_review_required` concerns whether official prose can be objectively machine-scored. It is not the cause of these seven failures: none reached an answer that could be manually compared with the official entity/name prose.

## Interpretation of the 0/9 result

The reported `0 / 9` is a real outcome for the frozen Development Planner plus deterministic Engine pipeline: it produced no valid plan for any scoreable supported case. It must not be read as evidence that numeric comparison, metre/millimetre normalization, or tolerance handling rejected otherwise correct answers. Those mechanisms were never invoked in these cases.

The audit separates two limits. Five width questions require a generic aggregate field that the external IFC model catalogs do not expose under the simplified `width` name. IDs 85 and 336 additionally show that the frozen classification assumed an empty-set or missing-data response which the Planner cannot initiate under its catalog checks. These seven should be treated as end-to-end support-boundary mismatches.

The other nine cases use normal comparative language or implicit domain semantics: `narrowest`, `widest`, `tallest`, and “largest room” (where area is implicit). They are direct external Planner generalization failures under the frozen implementation. The deterministic Engine was not tested on an alternative hand-written plan in this audit, so this report makes no claim that Engine execution would fail if supplied a valid plan.

## Audit boundary

This is a diagnosis of the frozen held-out run only. It does not revise the external metrics, add benchmark-specific behavior, or assign correctness to the 255 pre-classified unsupported cases. The source records remain [development_planner_results.json](development_planner_results.json), [external_cases.json](external_cases.json), and [classification_protocol.json](classification_protocol.json).
