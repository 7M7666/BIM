import os
from collections import Counter
from pathlib import Path

import pytest

from bim_evidence_qa.application import run_question
from bim_evidence_qa.domain import (
    AggregateFunction,
    BuildingDataset,
    BuildingEntity,
    FilterCondition,
    FilterOperator,
    QueryOperation,
    QueryPlan,
    ResolutionError,
)
from bim_evidence_qa.parsers import IfcOpenShellParser
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


def test_catalog_attributes_are_kind_aware(catalog):
    assert catalog.attributes_by_kind == {
        "storey": frozenset(),
        "space": frozenset({"area"}),
        "door": frozenset({"width"}),
    }
    assert catalog.supports_attribute("space", "area") is True
    assert catalog.supports_attribute("door", "width") is True
    assert catalog.supports_attribute("door", "area") is False


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


@pytest.mark.parametrize("question", ("What is the total room area?", "所有房间的总面积是多少？"))
def test_total_area_question_creates_sum_plan(planner, catalog, question):
    plan = planner.plan(question, catalog)

    assert plan.operation is QueryOperation.AGGREGATE
    assert plan.kind == "space"
    assert plan.aggregate_function is AggregateFunction.SUM
    assert plan.aggregate_field == "area"


def test_find_room_question_creates_find_plan(planner, catalog):
    plan = planner.plan("Find Room 101", catalog)

    assert plan.operation is QueryOperation.FIND
    assert plan.name == "Room 101"


def test_door_count_question_creates_count_plan(planner, catalog):
    plan = planner.plan("How many doors are there?", catalog)

    assert plan.operation is QueryOperation.COUNT
    assert plan.kind == "door"


def test_chinese_project_overview_phrases_create_the_same_plan(planner, catalog):
    plans = [
        planner.plan(question, catalog)
        for question in (
            "这个建筑有什么？",
            "这个模型包含什么？",
            "这个模型包含哪些构件？",
            "有哪些构件？",
            "给我概览一下这个项目。",
        )
    ]

    assert plans == [QueryPlan(QueryOperation.OVERVIEW)] * len(plans)


def test_english_project_overview_phrases_create_the_same_plan(planner, catalog):
    plans = [
        planner.plan(question, catalog)
        for question in (
            "What does this building contain?",
            "What kinds of elements are in this model?",
            "Give me an overview of this model.",
            "Give me a project overview.",
        )
    ]

    assert plans == [QueryPlan(QueryOperation.OVERVIEW)] * len(plans)


def test_overview_does_not_capture_a_specific_entity_count(planner, catalog):
    plan = planner.plan("How many doors are there?", catalog)

    assert plan == QueryPlan(QueryOperation.COUNT, kind="door")


def test_overview_uses_each_course_model_real_entity_counts():
    folder = os.getenv("BIM_QA_COURSE_DATA")
    if not folder:
        pytest.skip("Set BIM_QA_COURSE_DATA to the extracted teacher IFC folder")

    parser = IfcOpenShellParser()
    overview_kinds = {
        "storey", "space", "door", "window", "wall", "beam", "column", "slab",
        "footing", "pile",
    }
    datasets = {
        name: parser.parse(Path(folder) / name)
        for name in (
            "rac_basic_sample_project.ifc",
            "rst_basic_sample_project.ifc",
        )
    }
    outcomes = {
        name: run_question(
            datasets[name],
            question,
            DevelopmentNaturalLanguagePlanner(),
        )
        for name, question in (
            ("rac_basic_sample_project.ifc", "What does this building contain?"),
            ("rst_basic_sample_project.ifc", "这个模型包含哪些构件？"),
        )
    }

    for name, outcome in outcomes.items():
        expected = {
            kind: count
            for kind, count in Counter(
                entity.kind for entity in datasets[name].entities
            ).items()
            if kind in overview_kinds and count > 0
        }
        assert outcome.plan == QueryPlan(QueryOperation.OVERVIEW)
        assert outcome.result.overview_counts == expected
        assert all(count > 0 for count in outcome.result.overview_counts.values())

    assert "storey" not in outcomes["rst_basic_sample_project.ifc"].result.overview_counts


def test_course_storey_count_uses_only_ifc_building_storey_entities():
    folder = os.getenv("BIM_QA_COURSE_DATA")
    if not folder:
        pytest.skip("Set BIM_QA_COURSE_DATA to the extracted teacher IFC folder")

    parser = IfcOpenShellParser()
    rac = parser.parse(Path(folder) / "rac_basic_sample_project.ifc")
    rst = parser.parse(Path(folder) / "rst_basic_sample_project.ifc")
    planner = DevelopmentNaturalLanguagePlanner()

    rac_outcome = run_question(rac, "有几层楼？", planner)
    assert rac_outcome.plan == QueryPlan(QueryOperation.COUNT, kind="storey")
    assert rac_outcome.result.value == sum(entity.kind == "storey" for entity in rac.entities)

    with pytest.raises(ResolutionError) as error:
        planner.plan("有几层楼？", QueryCatalog.from_dataset(rst))
    assert error.value.code == "missing_storey_data"


def test_unknown_entity_is_rejected(planner, catalog):
    with pytest.raises(UnsupportedQueryError, match="supported entity kind"):
        planner.plan("How many elevators are there?", catalog)


def test_unknown_attribute_is_rejected(planner, catalog):
    with pytest.raises(
        UnsupportedQueryError,
        match="Attribute 'color' is not available",
    ):
        planner.plan("What color is Room 101?", catalog)


def test_attribute_from_another_entity_kind_is_rejected(planner, catalog):
    with pytest.raises(
        UnsupportedQueryError,
        match="Attribute 'area' is not available for entity kind 'door'",
    ):
        planner.plan("What is the average door area?", catalog)


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


def _hardening_dataset():
    return BuildingDataset(
        entities=(
            BuildingEntity("rac-storey", "storey", name="Level 1"),
            BuildingEntity("rac-slab", "slab", name="Slab:100001", container_id="rac-storey"),
            BuildingEntity("wall-1", "wall", attributes={"height": 3.0}),
            BuildingEntity("wall-2", "wall", attributes={"height": 4.0}),
            BuildingEntity("footing-1", "footing", name="Footing:200001"),
            BuildingEntity("beam-1046268", "beam", name="Beam:1046268", attributes={"length": 6.0}),
            BuildingEntity("beam-2", "beam", attributes={"length": 4.0}),
            BuildingEntity("space-1", "space", attributes={"area": 20.0}),
            BuildingEntity("space-2", "space", attributes={"area": 30.0}),
        )
    )


def test_semantic_equivalence_uses_canonical_plans_across_languages():
    planner = DevelopmentNaturalLanguagePlanner()
    catalog = QueryCatalog.from_dataset(_hardening_dataset())

    equivalents = {
        QueryPlan(QueryOperation.OVERVIEW): (
            "这个建筑有什么", "模型里都包含什么", "Give me an overview of this model",
        ),
        QueryPlan(QueryOperation.COUNT, kind="wall"): (
            "有多少墙", "几面墙", "How many walls are there",
        ),
        QueryPlan(QueryOperation.FIND, kind="footing"): (
            "有哪些基础", "四个基础是什么", "List the footings",
        ),
        QueryPlan(QueryOperation.LOCATION, kind="slab"): (
            "楼板在哪层", "这些 slabs belong to which level", "Which level contains the slabs",
        ),
    }

    for expected, questions in equivalents.items():
        assert [planner.plan(question, catalog) for question in questions] == [expected] * len(questions)


def test_filter_and_aggregate_synonyms_use_existing_engine_fields():
    planner = DevelopmentNaturalLanguagePlanner()
    catalog = QueryCatalog.from_dataset(_hardening_dataset())

    expected_filter = QueryPlan(
        QueryOperation.FILTER, kind="space",
        filters=(FilterCondition("area", FilterOperator.GT, 20),),
    )
    assert [planner.plan(question, catalog) for question in (
        "面积大于 20 的房间", "rooms with area > 20", "空间 area > 20",
    )] == [expected_filter] * 3

    expected_aggregate = QueryPlan(
        QueryOperation.AGGREGATE, kind="beam",
        aggregate_function=AggregateFunction.MAX, aggregate_field="length",
    )
    assert [planner.plan(question, catalog) for question in (
        "最长的梁", "Which beam is longest", "beam max length",
    )] == [expected_aggregate] * 3


def test_quantity_is_not_an_element_number_but_explicit_ids_are_find_queries():
    planner = DevelopmentNaturalLanguagePlanner()
    catalog = QueryCatalog.from_dataset(_hardening_dataset())

    assert planner.plan("四个基础是什么", catalog) == QueryPlan(QueryOperation.FIND, kind="footing")
    assert planner.plan("Find element number 1046268", catalog) == QueryPlan(
        QueryOperation.FIND, kind="beam",
        filters=(FilterCondition("entity_id", FilterOperator.EQ, "beam-1046268"),),
    )


def test_level_location_distinguishes_spatial_containment_and_reference_level():
    planner = DevelopmentNaturalLanguagePlanner()
    rac = BuildingDataset((
        BuildingEntity("rac-storey", "storey", name="Level 1"),
        BuildingEntity("rac-slab", "slab", container_id="rac-storey"),
    ))
    rst = BuildingDataset((
        BuildingEntity("rst-beam", "beam", attributes={"Constraints.Reference Level": "Level 2"}),
        BuildingEntity("rst-slab", "slab"),
    ))

    rac_result = QueryEngine().execute(
        planner.plan("楼板在哪层", QueryCatalog.from_dataset(rac)), rac,
    )
    assert rac_result.locations["rac-slab"].source == "spatial_containment"
    assert rac_result.locations["rac-slab"].level == "Level 1"

    rst_result = QueryEngine().execute(
        planner.plan("Which level contains the beams", QueryCatalog.from_dataset(rst)), rst,
    )
    assert rst_result.locations["rst-beam"].source == "reference_level"
    assert rst_result.locations["rst-beam"].level == "Level 2"

    with pytest.raises(ResolutionError) as error:
        QueryEngine().execute(planner.plan("楼板在哪层", QueryCatalog.from_dataset(rst)), rst)
    assert error.value.code == "missing_data"
