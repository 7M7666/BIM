"""Phase 2 regressions; set BIM_QA_COURSE_DATA to the extracted teacher IFC folder."""

import json
import os
import subprocess
import sys
from pathlib import Path

import ifcopenshell
import pytest
from ifcopenshell.util.element import get_container, get_psets

from bim_evidence_qa.application import run_question
from bim_evidence_qa.domain import BuildingDataset, BuildingEntity, FilterOperator
from bim_evidence_qa.parsers import IfcOpenShellParser
from bim_evidence_qa.query import (
    DevelopmentNaturalLanguagePlanner, InvalidPlannerOutputError,
    LLMQueryPlanner, QueryCatalog, UnsupportedQueryError,
)
from bim_evidence_qa.query.catalog import LevelResolutionError, REFERENCE_LEVEL_FIELD


@pytest.fixture
def levels_dataset():
    return BuildingDataset((
        BuildingEntity("s1", "storey", "Level 1"),
        BuildingEntity("s2", "storey", "Level 2"),
        BuildingEntity("s3", "storey", "Level 1 Living Rm."),
        BuildingEntity("b1", "beam", "Beam A", "G-B1", "s2",
                       {REFERENCE_LEVEL_FIELD: "Level 1"}),
        BuildingEntity("b2", "beam", "Beam B", "G-B2", "s1",
                       {REFERENCE_LEVEL_FIELD: "Level 2"}),
        BuildingEntity("d1", "door", "Door A", "G-D1", "s1"),
        BuildingEntity("d2", "door", "Door B", "G-D2", None),
    ))


@pytest.mark.parametrize("name", ["Level 2", "LEVEL 2", "  level   2  "])
def test_level_resolver_normalizes_exact_names(levels_dataset, name):
    condition = QueryCatalog.from_dataset(levels_dataset).resolve_level(name)
    assert (condition.field, condition.operator, condition.value) == (
        "container_id", FilterOperator.EQ, "s2",
    )


@pytest.mark.parametrize("names", [("Level 2", "Level 2"), ("Level 2", "LEVEL   2")])
def test_level_resolver_rejects_ambiguous_names(names):
    catalog = QueryCatalog.from_dataset(BuildingDataset(tuple(
        BuildingEntity(str(i), "storey", name) for i, name in enumerate(names)
    )))
    with pytest.raises(LevelResolutionError, match="Ambiguous"):
        catalog.resolve_level("Level 2")


@pytest.mark.parametrize("name", ["Level", "Level 20", "2"])
def test_level_resolver_does_not_fuzzy_match(levels_dataset, name):
    with pytest.raises(LevelResolutionError, match="not found"):
        QueryCatalog.from_dataset(levels_dataset).resolve_level(name)


@pytest.mark.parametrize("question,kind,value,field", [
    ("How many beams are on Level 2?", "beam", 1, "container_id"),
    ("Count doors in LEVEL 1.", "door", 1, "container_id"),
    ("How many beams have Reference Level = level 2?", "beam", 1, REFERENCE_LEVEL_FIELD),
    ("How many levels are there?", "storey", 3, None),
    ("List all beams on Level 2", "beam", None, "container_id"),
])
def test_subject_and_scope_are_separate(levels_dataset, question, kind, value, field):
    outcome = run_question(levels_dataset, question, DevelopmentNaturalLanguagePlanner())
    assert outcome.plan.kind == kind
    assert outcome.answer.value == value
    if field:
        assert outcome.plan.filters[0].field == field
        assert len(outcome.answer.evidence) == 1
        if field == REFERENCE_LEVEL_FIELD:
            assert outcome.answer.evidence[0].global_id == "G-B2"
            assert "Property-based level" in outcome.answer.text
            assert "not IfcBuildingStorey containment" in outcome.answer.text
        else:
            assert "Spatial containment: IfcBuildingStorey" in outcome.answer.text


def test_no_containment_is_not_guessed_from_name_or_reference_level():
    dataset = BuildingDataset((
        BuildingEntity("s", "storey", "Level 2"),
        BuildingEntity("b", "beam", "Beam on Level 2", attributes={REFERENCE_LEVEL_FIELD: "Level 2"}),
    ))
    result = run_question(dataset, "Count beams on Level 2", DevelopmentNaturalLanguagePlanner())
    assert result.answer.value == 0
    assert result.answer.evidence == ()


@pytest.mark.parametrize("question", [
    "Count beams and doors", "How many beams are on Missing Level?",
    "Which IfcBuildingStorey contains these beams?", "Show the properties of Beam A",
])
def test_ambiguous_missing_and_out_of_scope_queries_are_rejected(levels_dataset, question):
    with pytest.raises(UnsupportedQueryError):
        run_question(levels_dataset, question, DevelopmentNaturalLanguagePlanner())


def test_reference_level_name_ambiguity_is_not_silently_merged():
    dataset = BuildingDataset(tuple(
        BuildingEntity(str(i), "beam", attributes={REFERENCE_LEVEL_FIELD: name})
        for i, name in enumerate(("Level 2", "LEVEL 2"))
    ))
    with pytest.raises(LevelResolutionError, match="Ambiguous"):
        QueryCatalog.from_dataset(dataset).resolve_level("Level 2", reference=True, kind="beam")


@pytest.mark.parametrize("seed", ["1", "17", "999"])
def test_entity_detection_is_stable_across_hash_seeds(seed):
    source = """
from bim_evidence_qa.domain import BuildingDataset, BuildingEntity
from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner, QueryCatalog
dataset = BuildingDataset((BuildingEntity('s', 'storey', 'Level 2'), BuildingEntity('b', 'beam')))
plan = DevelopmentNaturalLanguagePlanner().plan('How many beams are on Level 2?', QueryCatalog.from_dataset(dataset))
assert plan.kind == 'beam'
assert plan.filters[0].value == 's'
"""
    result = subprocess.run(
        [sys.executable, "-c", source],
        env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_existing_aggregate_can_use_spatial_scope(synthetic_dataset):
    outcome = run_question(synthetic_dataset, "What is the average room area on Level 2?",
                           DevelopmentNaturalLanguagePlanner())
    selected = [e for e in synthetic_dataset.entities if e.kind == "space" and e.container_id == "storey-level-2"]
    assert outcome.answer.value == sum(e.attributes["area"] for e in selected) / len(selected)
    assert "Spatial containment" in outcome.answer.text


@pytest.mark.parametrize("mode", ["direct", "aggregate", "nested", "space", "cycle", "uncontained", "conflict", "site"])
def test_ifc_containment_traversal_handles_chains_and_invalid_paths(tmp_path, mode):
    model = ifcopenshell.file(schema="IFC4")
    door = model.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="Door")
    storey = model.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="Level A")
    parent = model.create_entity("IfcCurtainWall", GlobalId=ifcopenshell.guid.new())

    def aggregate(child, container, relation="IfcRelAggregates"):
        model.create_entity(relation, GlobalId=ifcopenshell.guid.new(),
                            RelatedObjects=[child], RelatingObject=container)

    def contain(child, container):
        model.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(),
                            RelatedElements=[child], RelatingStructure=container)

    expected = storey
    if mode == "direct":
        contain(door, storey)
    elif mode in {"aggregate", "nested"}:
        intermediate = model.create_entity("IfcElementAssembly", GlobalId=ifcopenshell.guid.new())
        aggregate(door, intermediate, "IfcRelNests" if mode == "nested" else "IfcRelAggregates")
        aggregate(intermediate, parent)
        contain(parent, storey)
    elif mode == "space":
        space = model.create_entity("IfcSpace", GlobalId=ifcopenshell.guid.new())
        contain(door, space)
        aggregate(space, storey)
    elif mode == "cycle":
        aggregate(door, parent)
        aggregate(parent, door)
        expected = None
    elif mode == "uncontained":
        aggregate(door, parent)
        expected = None
    elif mode == "conflict":
        other = model.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new())
        contain(door, storey)
        contain(door, other)
        expected = None
    else:
        expected = model.create_entity("IfcSite", GlobalId=ifcopenshell.guid.new(), Name="Default")
        contain(door, expected)
    path = tmp_path / "containment.ifc"
    model.write(str(path))
    normalized = next(e for e in IfcOpenShellParser().parse(path).entities if e.kind == "door")
    assert normalized.container_id == (f"ifc-{expected.id()}" if expected else None)


class FixedProvider:
    def __init__(self, payload):
        self.payload = payload

    def complete(self, system_prompt, user_prompt):
        return json.dumps(self.payload)


@pytest.mark.parametrize("field,value,question", [
    ("storey_name", "  LEVEL   2 ", "How many beams are on Level 2?"),
    ("reference_level", "level 2", "How many beams have Reference Level Level 2?"),
])
def test_llm_level_names_are_resolved_locally(levels_dataset, field, value, question):
    planner = LLMQueryPlanner(FixedProvider({
        "operation": "count", "kind": "beam",
        "filters": [{"field": field, "operator": "eq", "value": value}],
    }))
    outcome = run_question(levels_dataset, question, planner)
    assert outcome.answer.value == 1
    assert outcome.answer.evidence[0].global_id == ("G-B1" if field == "storey_name" else "G-B2")


@pytest.mark.parametrize("payload", [
    {"operation": "count", "kind": "storey"},
    {"operation": "count", "kind": "beam"},
    {"operation": "count", "kind": "beam", "filters": [{"field": "storey_name", "operator": "eq", "value": "Level 1"}]},
    {"operation": "count", "kind": "beam", "filters": [{"field": "container_id", "operator": "eq", "value": "s2"}]},
    {"operation": "count", "kind": "beam", "filters": [{"field": "reference_level", "operator": "eq", "value": "Level 2"}]},
])
def test_llm_cannot_change_subject_omit_scope_or_guess_id(levels_dataset, payload):
    with pytest.raises(InvalidPlannerOutputError):
        run_question(levels_dataset, "How many beams are on Level 2?", LLMQueryPlanner(FixedProvider(payload)))


@pytest.mark.parametrize("storeys", [(), (
    BuildingEntity("s1", "storey", "Level 2"), BuildingEntity("s2", "storey", "LEVEL 2"),
)])
def test_llm_rejects_absent_and_ambiguous_storeys(storeys):
    dataset = BuildingDataset((*storeys, BuildingEntity("b", "beam", container_id="site")))
    provider = FixedProvider({"operation": "count", "kind": "beam", "filters": [
        {"field": "storey_name", "operator": "eq", "value": "Level 2"},
    ]})
    with pytest.raises(InvalidPlannerOutputError):
        run_question(dataset, "How many beams are on Level 2?", LLMQueryPlanner(provider))


@pytest.fixture(scope="module")
def course_models():
    folder = os.getenv("BIM_QA_COURSE_DATA")
    if not folder:
        pytest.skip("Set BIM_QA_COURSE_DATA to the extracted teacher IFC folder")
    models = {}
    for label in ("rac", "rst"):
        path = Path(folder) / f"{label}_basic_sample_project.ifc"
        assert path.is_file(), f"Course IFC not found: {path}"
        models[label] = (ifcopenshell.open(str(path)), IfcOpenShellParser().parse(path))
    return models


@pytest.mark.parametrize("label,kind,ifc_type,expected", [
    ("rac", "door", "IfcDoor", 16), ("rac", "window", "IfcWindow", 17),
    ("rac", "wall", "IfcWall", 47), ("rac", "column", "IfcColumn", 3),
    ("rac", "slab", "IfcSlab", 12), ("rac", "pile", "IfcPile", 23),
    ("rst", "beam", "IfcBeam", 370), ("rst", "column", "IfcColumn", 30),
    ("rst", "slab", "IfcSlab", 5), ("rst", "footing", "IfcFooting", 4),
    ("rst", "pile", "IfcPile", 32),
])
def test_course_entity_queries_preserve_raw_facts(course_models, label, kind, ifc_type, expected):
    model, dataset = course_models[label]
    raw = model.by_type(ifc_type)
    assert len(raw) == expected
    outcome = run_question(dataset, f"How many {kind}s are there?", DevelopmentNaturalLanguagePlanner())
    assert outcome.plan.kind == kind
    assert outcome.answer.value == expected
    assert {e.global_id for e in outcome.answer.evidence} == {e.GlobalId for e in raw}
    normalized = {e.global_id: e for e in outcome.result.entities}
    for source in raw:
        entity = normalized[source.GlobalId]
        assert entity.name == source.Name
        for name, properties in get_psets(source).items():
            for key, value in properties.items():
                if key != "id" and (value is None or isinstance(value, (str, int, float, bool))):
                    assert entity.attributes[f"{name}.{key}"] == value
    listed = run_question(dataset, f"List all {kind}s.", DevelopmentNaturalLanguagePlanner())
    assert {e.global_id for e in listed.answer.evidence} == set(normalized)


@pytest.mark.parametrize("level,expected", [("Level 1", 4), ("Level 1 Living Rm.", 2), ("Level 2", 10)])
def test_course_rac_indirect_door_containment(course_models, level, expected):
    model, dataset = course_models["rac"]
    raw = [e for e in model.by_type("IfcDoor") if get_container(e).Name == level]
    outcome = run_question(dataset, f"How many doors are on {level}?", DevelopmentNaturalLanguagePlanner())
    assert outcome.answer.value == len(raw) == expected
    assert {e.global_id for e in outcome.answer.evidence} == {e.GlobalId for e in raw}
    assert "Spatial containment" in outcome.answer.text


@pytest.mark.parametrize("level,expected", [
    ("Top of Parapet", 144), ("Level 2", 84), ("Foundation", 39),
    ("Level 1", 30), ("Level Lower", 73),
])
def test_course_rst_property_based_reference_level(course_models, level, expected):
    model, dataset = course_models["rst"]
    assert model.by_type("IfcBuildingStorey") == []
    assert model.by_type("IfcBuilding") == []
    raw = [e for e in model.by_type("IfcBeam") if get_psets(e)["Constraints"]["Reference Level"] == level]
    outcome = run_question(dataset, f"How many beams have Reference Level {level}?", DevelopmentNaturalLanguagePlanner())
    assert outcome.answer.value == len(raw) == expected
    assert {e.global_id for e in outcome.answer.evidence} == {e.GlobalId for e in raw}
    assert outcome.plan.filters[0].field == REFERENCE_LEVEL_FIELD
    assert "Property-based level" in outcome.answer.text
    assert "not IfcBuildingStorey containment" in outcome.answer.text
    for entity in outcome.result.entities:
        container = model.by_id(int(entity.container_id.removeprefix("ifc-")))
        assert container.is_a("IfcSite")


@pytest.mark.parametrize("question", [
    "How many beams are on Level 2?", "Which IfcBuildingStorey contains these beams?",
])
def test_course_rst_never_invents_storey_containment(course_models, question):
    with pytest.raises(UnsupportedQueryError):
        run_question(course_models["rst"][1], question, DevelopmentNaturalLanguagePlanner())


def test_course_rac_absent_beams_do_not_become_storeys(course_models):
    with pytest.raises(UnsupportedQueryError, match="beam"):
        run_question(course_models["rac"][1], "How many beams are on Level 2?", DevelopmentNaturalLanguagePlanner())
