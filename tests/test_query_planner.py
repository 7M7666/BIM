import pytest

from bim_evidence_qa.domain import (
    AggregateFunction,
    BuildingDataset,
    BuildingEntity,
    QueryOperation,
)
from bim_evidence_qa.query import (
    DevelopmentNaturalLanguagePlanner,
    QueryCatalog,
    QueryEngine,
    UnsupportedQueryError,
)


@pytest.fixture
def catalog(synthetic_dataset):
    return QueryCatalog.from_dataset(synthetic_dataset)


@pytest.fixture
def planner():
    return DevelopmentNaturalLanguagePlanner()


def test_query_catalog_is_generated_from_dataset_content():
    dataset = BuildingDataset(
        entities=(
            BuildingEntity(
                entity_id="beam-1",
                kind="beam",
                name="Beam 1",
                global_id="SYNTHETIC-BEAM-1",
                attributes={"length": 4.5},
            ),
        )
    )

    catalog = QueryCatalog.from_dataset(dataset)

    assert catalog.kinds == {"beam"}
    assert catalog.attributes == {"length"}
    assert "space" not in catalog.kinds
    assert "area" not in catalog.attributes


def test_catalog_discovers_fixture_kinds(catalog):
    assert catalog.kinds == {"storey", "space", "door"}


def test_catalog_discovers_fixture_attributes(catalog):
    assert catalog.attributes == {"area", "width"}


def test_catalog_discovers_names_containers_and_operations(catalog):
    assert "Room 202" in catalog.entity_names
    assert catalog.container_ids == {"storey-level-1", "storey-level-2"}
    assert catalog.container_names == {"Level 1", "Level 2"}
    assert catalog.operations == set(QueryOperation)


def test_room_count_question_creates_count_plan(planner, catalog):
    plan = planner.plan("How many rooms are there?", catalog)

    assert plan.operation is QueryOperation.COUNT
    assert plan.kind == "space"


def test_largest_room_question_creates_max_plan(planner, catalog):
    plan = planner.plan("Which room has the largest area?", catalog)

    assert plan.operation is QueryOperation.AGGREGATE
    assert plan.kind == "space"
    assert plan.aggregate_function is AggregateFunction.MAX
    assert plan.aggregate_field == "area"


def test_average_room_area_question_creates_average_plan(planner, catalog):
    plan = planner.plan("What is the average room area?", catalog)

    assert plan.operation is QueryOperation.AGGREGATE
    assert plan.kind == "space"
    assert plan.aggregate_function is AggregateFunction.AVERAGE
    assert plan.aggregate_field == "area"


def test_find_room_question_creates_find_plan(planner, catalog):
    plan = planner.plan("Find Room 101", catalog)

    assert plan.operation is QueryOperation.FIND
    assert plan.name == "Room 101"


def test_door_count_question_creates_count_plan(planner, catalog):
    plan = planner.plan("How many doors are there?", catalog)

    assert plan.operation is QueryOperation.COUNT
    assert plan.kind == "door"


def test_unknown_entity_is_rejected(planner, catalog):
    with pytest.raises(UnsupportedQueryError, match="supported entity kind"):
        planner.plan("How many elevators are there?", catalog)


def test_unknown_attribute_is_rejected(planner, catalog):
    with pytest.raises(
        UnsupportedQueryError,
        match="Attribute 'color' is not available",
    ):
        planner.plan("What color is Room 101?", catalog)


def test_planned_query_executes_without_translation(
    planner, catalog, synthetic_dataset
):
    plan = planner.plan("How many rooms are there?", catalog)
    result = QueryEngine().execute(plan, synthetic_dataset)

    assert result.value == 5


def test_natural_language_max_query_preserves_dataset_fact_and_global_id(
    planner, catalog, synthetic_dataset
):
    plan = planner.plan("Which room has the largest area?", catalog)
    result = QueryEngine().execute(plan, synthetic_dataset)

    assert result.value == 30.0
    assert [entity.name for entity in result.entities] == ["Room 202"]
    assert result.entities[0].global_id == "SYNTHETIC-SPACE-202"
