import ifcopenshell
import pytest

from bim_evidence_qa.application import run_question
from bim_evidence_qa.domain import BuildingDataset
from bim_evidence_qa.parsers import IFCParseError, IfcOpenShellParser
from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner, QueryCatalog


def test_development_fixture_is_a_real_ifc_file(development_ifc_path):
    model = ifcopenshell.open(str(development_ifc_path))

    assert model.schema == "IFC4"
    assert len(model.by_type("IfcSpace")) == 3


def test_ifc_standard_entities_are_normalized(development_ifc_dataset):
    counts = {
        kind: sum(
            entity.kind == kind for entity in development_ifc_dataset.entities
        )
        for kind in ("storey", "space", "door", "window", "wall")
    }

    assert counts == {
        "storey": 2,
        "space": 3,
        "door": 2,
        "window": 1,
        "wall": 1,
    }


def test_ifc_internal_id_and_global_id_are_distinct_and_preserved(
    development_ifc_dataset,
):
    room_101 = next(
        entity
        for entity in development_ifc_dataset.entities
        if entity.name == "Room 101"
    )

    assert room_101.entity_id == "ifc-4"
    assert room_101.global_id == "0000000000000000000004"
    assert room_101.entity_id != room_101.global_id


def test_ifc_spatial_containment_is_preserved(development_ifc_dataset):
    by_name = {
        entity.name: entity
        for entity in development_ifc_dataset.entities
        if entity.name is not None
    }

    assert by_name["Room 101"].container_id == by_name["Level 1"].entity_id
    assert by_name["Door D201"].container_id == by_name["Level 2"].entity_id
    assert by_name["Window W101"].container_id == by_name["Level 1"].entity_id
    assert by_name["Wall W001"].container_id == by_name["Level 1"].entity_id


def test_ifc_missing_name_is_accepted(development_ifc_dataset):
    unnamed_spaces = [
        entity
        for entity in development_ifc_dataset.entities
        if entity.kind == "space" and entity.name is None
    ]

    assert len(unnamed_spaces) == 1
    assert unnamed_spaces[0].global_id == "0000000000000000000006"


def test_ifc_missing_global_id_is_not_generated(tmp_path, development_ifc_path):
    path = tmp_path / "missing-global-id.ifc"
    source = development_ifc_path.read_text(encoding="utf-8")
    path.write_text(
        source.replace("'0000000000000000000004'", "$", 1),
        encoding="utf-8",
    )

    dataset = IfcOpenShellParser().parse(path)

    room_101 = next(
        entity for entity in dataset.entities if entity.name == "Room 101"
    )
    assert room_101.global_id is None


def test_ifc_missing_containment_is_not_inferred(tmp_path):
    model = ifcopenshell.file(schema="IFC4")
    model.create_entity(
        "IfcDoor",
        GlobalId="000000000000000000000Z",
        Name="Uncontained Door",
    )
    path = tmp_path / "uncontained.ifc"
    model.write(str(path))

    dataset = IfcOpenShellParser().parse(path)

    assert dataset.entities[0].container_id is None


def test_invalid_ifc_reports_a_real_parse_error(tmp_path):
    path = tmp_path / "broken.ifc"

    with pytest.raises(IFCParseError, match="Cannot parse IFC"):
        IfcOpenShellParser().parse(path)


def test_ifc_actual_property_sets_and_quantities_are_discovered(
    development_ifc_dataset,
):
    by_name = {
        entity.name: entity
        for entity in development_ifc_dataset.entities
        if entity.name is not None
    }

    assert (
        by_name["Door D101"].attributes[
            "DevelopmentDoorProperties.FireRating"
        ]
        == "FD30"
    )
    assert (
        by_name["Room 101"].attributes[
            "DevelopmentSpaceQuantities.MeasuredArea"
        ]
        == 18.5
    )
    assert by_name["Room 102"].attributes == {}


def test_real_ifc_dataset_builds_existing_query_catalog(
    development_ifc_dataset,
):
    catalog = QueryCatalog.from_dataset(development_ifc_dataset)

    assert catalog.kinds == {"storey", "space", "door", "window", "wall"}
    assert "Room 101" in catalog.entity_names


def test_real_ifc_enters_existing_question_answer_pipeline(
    development_ifc_dataset,
):
    outcome = run_question(
        development_ifc_dataset,
        "How many rooms are there?",
        DevelopmentNaturalLanguagePlanner(),
    )

    assert isinstance(development_ifc_dataset, BuildingDataset)
    assert outcome.answer.text == "There are 3 spaces."
    assert outcome.answer.value == 3
    assert {
        item.global_id for item in outcome.answer.evidence
    } == {
        "0000000000000000000004",
        "0000000000000000000005",
        "0000000000000000000006",
    }
