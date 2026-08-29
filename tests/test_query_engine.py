import pytest

from bim_evidence_qa.domain import (
    AggregateFunction,
    BuildingDataset,
    BuildingEntity,
    FilterCondition,
    FilterOperator,
    QueryOperation,
    QueryPlan,
)
from bim_evidence_qa.query import (
    IncompleteDataError,
    QueryEngine,
    UnknownFieldError,
)


@pytest.fixture
def engine() -> QueryEngine:
    return QueryEngine()


def test_find_entities_by_kind(engine, synthetic_dataset):
    result = engine.execute(
        QueryPlan(operation=QueryOperation.FIND, kind="door"),
        synthetic_dataset,
    )

    assert len(result.entities) == 4
    assert {entity.kind for entity in result.entities} == {"door"}


def test_find_entity_by_name(engine, synthetic_dataset):
    result = engine.execute(
        QueryPlan(operation=QueryOperation.FIND, name="Room 202"),
        synthetic_dataset,
    )

    assert [entity.entity_id for entity in result.entities] == ["space-202"]


def test_count_spaces(engine, synthetic_dataset):
    result = engine.execute(
        QueryPlan(operation=QueryOperation.COUNT, kind="space"),
        synthetic_dataset,
    )

    assert result.value == 5
    assert len(result.entities) == 5


def test_filter_spaces_by_area(engine, synthetic_dataset):
    result = engine.execute(
        QueryPlan(
            operation=QueryOperation.FILTER,
            kind="space",
            filters=(
                FilterCondition("area", FilterOperator.GT, 20),
            ),
        ),
        synthetic_dataset,
    )

    assert {entity.name for entity in result.entities} == {"Room 102", "Room 202"}


def test_filter_spaces_by_storey(engine, synthetic_dataset):
    result = engine.execute(
        QueryPlan(
            operation=QueryOperation.FILTER,
            kind="space",
            filters=(
                FilterCondition(
                    "container_id", FilterOperator.EQ, "storey-level-2"
                ),
            ),
        ),
        synthetic_dataset,
    )

    assert {entity.name for entity in result.entities} == {
        "Room 201",
        "Room 202",
        "Room 203",
    }


def test_find_space_with_maximum_area(engine, synthetic_dataset):
    result = engine.execute(
        QueryPlan(
            operation=QueryOperation.AGGREGATE,
            kind="space",
            aggregate_function=AggregateFunction.MAX,
            aggregate_field="area",
        ),
        synthetic_dataset,
    )

    assert result.value == 30.0
    assert [entity.name for entity in result.entities] == ["Room 202"]


def test_find_space_with_minimum_area(engine, synthetic_dataset):
    result = engine.execute(
        QueryPlan(
            operation=QueryOperation.AGGREGATE,
            kind="space",
            aggregate_function=AggregateFunction.MIN,
            aggregate_field="area",
        ),
        synthetic_dataset,
    )

    assert result.value == 12.0
    assert [entity.name for entity in result.entities] == ["Room 201"]


def test_average_space_area(engine, synthetic_dataset):
    result = engine.execute(
        QueryPlan(
            operation=QueryOperation.AGGREGATE,
            kind="space",
            aggregate_function=AggregateFunction.AVERAGE,
            aggregate_field="area",
        ),
        synthetic_dataset,
    )

    assert result.value == 21.0
    assert len(result.entities) == 5


def test_unknown_field_has_clear_error(engine, synthetic_dataset):
    plan = QueryPlan(
        operation=QueryOperation.FILTER,
        kind="space",
        filters=(FilterCondition("ceiling_height", FilterOperator.GT, 2.5),),
    )

    with pytest.raises(
        UnknownFieldError,
        match="Field 'ceiling_height' does not exist on entity 'space-101'",
    ):
        engine.execute(plan, synthetic_dataset)


def test_global_id_is_preserved_and_not_generated(engine, synthetic_dataset):
    result = engine.execute(
        QueryPlan(operation=QueryOperation.FIND, name="Room 202"),
        synthetic_dataset,
    )

    assert result.entities[0].global_id == "SYNTHETIC-SPACE-202"
    assert BuildingEntity(entity_id="without-global-id", kind="space").global_id is None


def test_partial_aggregate_attribute_coverage_is_explicit(engine):
    dataset = BuildingDataset(
        entities=(
            BuildingEntity("space-1", "space", attributes={"area": 10.0}),
            BuildingEntity("space-2", "space", attributes={"area": 20.0}),
            BuildingEntity("space-3", "space", attributes={}),
        )
    )
    plan = QueryPlan(
        operation=QueryOperation.AGGREGATE,
        kind="space",
        aggregate_function=AggregateFunction.MAX,
        aggregate_field="area",
    )

    with pytest.raises(IncompleteDataError) as captured:
        engine.execute(plan, dataset)

    error = captured.value
    assert error.field == "area"
    assert error.target_kind == "space"
    assert error.available_count == 2
    assert error.total_count == 3
    assert error.missing_entity_ids == ("space-3",)
    assert "cannot be answered reliably" in str(error)
