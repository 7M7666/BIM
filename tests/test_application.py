from bim_evidence_qa.application import run_question
from bim_evidence_qa.parsers import SyntheticFixtureParser
from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner


def test_development_planner_remains_offline_fallback(synthetic_dataset):
    outcome = run_question(
        synthetic_dataset,
        "How many rooms are there?",
        DevelopmentNaturalLanguagePlanner(),
    )

    assert outcome.result.value == 5
    assert outcome.answer.text == "There are 5 spaces."


def test_synthetic_fixture_enters_complete_application_flow(
    synthetic_fixture_path,
):
    dataset = SyntheticFixtureParser().parse(synthetic_fixture_path)

    outcome = run_question(
        dataset,
        "Which room has the largest area?",
        DevelopmentNaturalLanguagePlanner(),
    )

    assert outcome.result.value == outcome.answer.value == 30.0
    assert outcome.answer.text == "Room 202 has the maximum area: 30.0."


def test_application_evidence_global_id_comes_from_query_result(
    synthetic_dataset,
):
    outcome = run_question(
        synthetic_dataset,
        "Find Room 101",
        DevelopmentNaturalLanguagePlanner(),
    )

    assert outcome.answer.evidence[0].global_id == "SYNTHETIC-SPACE-101"
    assert (
        outcome.answer.evidence[0].global_id
        == outcome.result.entities[0].global_id
    )
