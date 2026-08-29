from dataclasses import dataclass

from bim_evidence_qa.answering import Answer, AnswerBuilder
from bim_evidence_qa.domain import BuildingDataset, QueryPlan, QueryResult
from bim_evidence_qa.query import QueryCatalog, QueryEngine, QueryPlanner


@dataclass(frozen=True, slots=True)
class ApplicationQueryResult:
    question: str
    plan: QueryPlan
    result: QueryResult
    answer: Answer


def run_question(
    dataset: BuildingDataset,
    question: str,
    planner: QueryPlanner,
) -> ApplicationQueryResult:
    catalog = QueryCatalog.from_dataset(dataset)
    plan = planner.plan(question, catalog)
    result = QueryEngine().execute(plan, dataset)
    answer = AnswerBuilder().build(plan, result)
    return ApplicationQueryResult(
        question=question,
        plan=plan,
        result=result,
        answer=answer,
    )
