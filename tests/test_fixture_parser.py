import json

import pytest

from bim_evidence_qa.domain import (
    AggregateFunction,
    BuildingDataset,
    QueryOperation,
    QueryPlan,
)
from bim_evidence_qa.parsers import FixtureParseError, SyntheticFixtureParser
from bim_evidence_qa.query import QueryEngine


def test_fixture_json_loads_as_building_dataset(synthetic_fixture_path):
    dataset = SyntheticFixtureParser().parse(synthetic_fixture_path)

    assert isinstance(dataset, BuildingDataset)


def test_entity_count_matches_json(synthetic_fixture_path):
    payload = json.loads(synthetic_fixture_path.read_text(encoding="utf-8"))
    dataset = SyntheticFixtureParser().parse(synthetic_fixture_path)

    assert len(dataset.entities) == len(payload["entities"]) == 11


def test_attributes_keep_json_scalar_types(synthetic_dataset):
    room_101 = next(
        entity for entity in synthetic_dataset.entities if entity.name == "Room 101"
    )
    door_d101 = next(
        entity for entity in synthetic_dataset.entities if entity.name == "Door D101"
    )

    assert room_101.attributes["area"] == 18.0
    assert isinstance(room_101.attributes["area"], float)
    assert door_d101.attributes["width"] == 0.9
    assert isinstance(door_d101.attributes["width"], float)


def test_global_ids_are_fully_preserved(synthetic_dataset):
    global_ids = {entity.global_id for entity in synthetic_dataset.entities}

    assert len(global_ids) == len(synthetic_dataset.entities)
    assert "SYNTHETIC-SPACE-202" in global_ids
    assert all(global_id.startswith("SYNTHETIC-") for global_id in global_ids)


def test_container_id_is_preserved(synthetic_dataset):
    room_202 = next(
        entity for entity in synthetic_dataset.entities if entity.name == "Room 202"
    )

    assert room_202.container_id == "storey-level-2"


def test_non_synthetic_fixture_is_rejected(tmp_path):
    fixture_path = tmp_path / "real-project.json"
    fixture_path.write_text(
        json.dumps(
            {
                "fixture_type": "real-project",
                "allowed_for_evaluation": False,
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        FixtureParseError,
        match="fixture_type must be 'synthetic-development-only'",
    ):
        SyntheticFixtureParser().parse(fixture_path)


def test_evaluation_enabled_fixture_is_rejected(tmp_path):
    fixture_path = tmp_path / "evaluation-enabled.json"
    fixture_path.write_text(
        json.dumps(
            {
                "fixture_type": "synthetic-development-only",
                "allowed_for_evaluation": True,
                "entities": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        FixtureParseError,
        match="allowed_for_evaluation must be false",
    ):
        SyntheticFixtureParser().parse(fixture_path)


def test_malformed_fixture_has_clear_error(tmp_path):
    fixture_path = tmp_path / "malformed.json"
    fixture_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(FixtureParseError, match="Malformed fixture JSON"):
        SyntheticFixtureParser().parse(fixture_path)


def test_loaded_dataset_can_be_queried_directly(synthetic_fixture_path):
    dataset = SyntheticFixtureParser().parse(synthetic_fixture_path)
    result = QueryEngine().execute(
        QueryPlan(operation=QueryOperation.COUNT, kind="space"),
        dataset,
    )

    assert result.value == 5


def test_max_area_query_after_file_load(synthetic_fixture_path):
    dataset = SyntheticFixtureParser().parse(synthetic_fixture_path)
    result = QueryEngine().execute(
        QueryPlan(
            operation=QueryOperation.AGGREGATE,
            kind="space",
            aggregate_function=AggregateFunction.MAX,
            aggregate_field="area",
        ),
        dataset,
    )

    assert result.value == 30.0
    assert [entity.name for entity in result.entities] == ["Room 202"]
    assert result.entities[0].global_id == "SYNTHETIC-SPACE-202"
