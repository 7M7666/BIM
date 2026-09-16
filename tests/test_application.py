import pytest

from bim_evidence_qa.application import (
    ConversationContext,
    resolve_follow_up_question,
    run_question,
)
from bim_evidence_qa.domain import (
    BuildingDataset,
    BuildingEntity,
    PropertySource,
    PropertyValue,
    ResolutionError,
)
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


def test_property_follow_up_resolves_the_previous_single_object(synthetic_dataset):
    dataset = BuildingDataset((
        BuildingEntity(
            "space-101",
            "space",
            name="Room 101",
            properties=(PropertyValue(
                PropertySource.QUANTITY,
                "Qto_SpaceBaseQuantities",
                "Area",
                18.0,
                unit="m2",
            ),),
        ),
    ))
    first = run_question(
        dataset,
        "Find Room 101",
        DevelopmentNaturalLanguagePlanner(),
    )

    follow_up = run_question(
        dataset,
        "那它的面积呢？",
        DevelopmentNaturalLanguagePlanner(),
        ConversationContext.from_outcome(first),
    )

    assert follow_up.plan.requested_property == "area"
    assert follow_up.result.entities[0].entity_id == "space-101"
    assert follow_up.result.value == 18.0


def test_storey_follow_up_narrows_the_previous_count(synthetic_dataset):
    first = run_question(
        synthetic_dataset,
        "How many doors are there?",
        DevelopmentNaturalLanguagePlanner(),
    )

    follow_up = run_question(
        synthetic_dataset,
        "只看第二层呢？",
        DevelopmentNaturalLanguagePlanner(),
        ConversationContext.from_outcome(first),
    )

    assert follow_up.plan.operation.value == "count"
    assert follow_up.plan.kind == "door"
    assert follow_up.result.value == 2


def test_location_follow_up_resolves_the_previous_single_object(synthetic_dataset):
    first = run_question(
        synthetic_dataset,
        "Find Door D101",
        DevelopmentNaturalLanguagePlanner(),
    )

    question = resolve_follow_up_question(
        "那它在哪一层？",
        ConversationContext.from_outcome(first),
    )

    assert question == "Which level contains Door D101?"


def test_follow_up_does_not_pick_one_object_from_a_previous_collection(synthetic_dataset):
    first = run_question(
        synthetic_dataset,
        "How many doors are there?",
        DevelopmentNaturalLanguagePlanner(),
    )

    with pytest.raises(ResolutionError, match="previous answer") as error:
        run_question(
            synthetic_dataset,
            "那它的宽度呢？",
            DevelopmentNaturalLanguagePlanner(),
            ConversationContext.from_outcome(first),
        )

    assert error.value.code == "needs_context"


def test_count_without_a_target_requests_clarification(synthetic_dataset):
    with pytest.raises(ResolutionError, match="Specify which") as error:
        run_question(
            synthetic_dataset,
            "帮我数一下",
            DevelopmentNaturalLanguagePlanner(),
        )

    assert error.value.code == "needs_context"
