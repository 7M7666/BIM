"""Property provenance and multilingual query regressions; no benchmark scoring."""

import json
from dataclasses import replace

import ifcopenshell
import pytest
from streamlit.testing.v1 import AppTest

from test_phase2 import course_models
from bim_evidence_qa.application import run_question
from bim_evidence_qa.domain import (
    BuildingDataset, BuildingEntity, PropertySource, PropertyValue, ResolutionError,
    QueryPlan, QueryOperation, FilterCondition, FilterOperator,
)
from bim_evidence_qa.parsers import IfcOpenShellParser
from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner, LLMQueryPlanner, InvalidPlannerOutputError, QueryEngine
from bim_evidence_qa.query.properties import resolve_property
from bim_evidence_qa.query.terminology import ENTITY_ALIASES, PROPERTY_ALIASES


def query(dataset, question):
    return run_question(dataset, question, DevelopmentNaturalLanguagePlanner())


@pytest.fixture
def bilingual_dataset():
    entities = [BuildingEntity("s", "storey", "Level 2", "GS")]
    for kind in sorted(set(ENTITY_ALIASES.values()) - {"storey"}):
        props = (
            PropertyValue(PropertySource.QUANTITY, f"Qto_{kind}", "Length", 4.5, "IfcLengthMeasure", "mm", 1),
            PropertyValue(PropertySource.QUANTITY, f"Qto_{kind}", "Width", 2.0, "IfcLengthMeasure", "mm", 2),
            PropertyValue(PropertySource.QUANTITY, f"Qto_{kind}", "Height", 3.0, "IfcLengthMeasure", "mm", 3),
            PropertyValue(PropertySource.QUANTITY, f"Qto_{kind}", "Area", 9.0, "IfcAreaMeasure", "m²", 4),
            PropertyValue(PropertySource.QUANTITY, f"Qto_{kind}", "NetVolume", 18.0, "IfcVolumeMeasure", "m³", 5),
        )
        entities.append(BuildingEntity(kind, kind, f"{kind.title()} X", f"G-{kind}", "s", properties=props))
    return BuildingDataset(tuple(entities))


@pytest.mark.parametrize("alias,kind", sorted(ENTITY_ALIASES.items()))
def test_chinese_entity_aliases_have_same_plan_answer_and_evidence(bilingual_dataset, alias, kind):
    english = query(bilingual_dataset, f"How many {kind}s are there?")
    chinese = query(bilingual_dataset, f"有多少{alias}？")
    mixed = query(bilingual_dataset, f"How many {alias} are there?")
    assert english.plan == chinese.plan == mixed.plan
    assert english.answer == chinese.answer == mixed.answer


@pytest.mark.parametrize("question", ["二层有多少扇门？", "Level 2 有多少 doors？", "第二层门的数量？", "2层有几扇门？"])
def test_multilingual_spatial_scope(bilingual_dataset, question):
    expected = query(bilingual_dataset, "How many doors are on Level 2?")
    actual = query(bilingual_dataset, question)
    assert actual.plan == expected.plan
    assert actual.answer == expected.answer


@pytest.mark.parametrize("question", ["列出所有楼板。", "显示所有slabs", "哪些板？"])
def test_multilingual_list(bilingual_dataset, question):
    expected = query(bilingual_dataset, "List all slabs.")
    actual = query(bilingual_dataset, question)
    assert actual.plan == expected.plan
    assert actual.answer == expected.answer


@pytest.mark.parametrize("english,chinese", [
    ("What is the maximum room area?", "房间的最大面积？"),
    ("What is the minimum room area?", "房间的最小面积？"),
    ("What is the average room area?", "房间面积的平均值？"),
])
def test_multilingual_existing_aggregates(synthetic_dataset, english, chinese):
    a, b = query(synthetic_dataset, english), query(synthetic_dataset, chinese)
    assert a.plan == b.plan
    assert a.answer == b.answer


@pytest.mark.parametrize("question", ["梁 X 的长度是多少？", "Beam X 有多长？", "What is the 长度 of Beam X?"])
def test_multilingual_property_plan_value_and_evidence(bilingual_dataset, question):
    expected = query(bilingual_dataset, "What is the length of Beam X?")
    actual = query(bilingual_dataset, question)
    assert actual.plan == expected.plan
    assert actual.plan.requested_property == "length"
    assert actual.answer == expected.answer
    assert actual.answer.value == 4.5
    assert actual.answer.evidence[0].properties[0].unit == "mm"


@pytest.mark.parametrize("question,code", [
    ("这个门的宽度是多少？", "needs_context"),
    ("这个 IfcBeam 的 Length 是多少？", "needs_context"),
    ("What is the length of Beam missing?", "entity_not_found"),
    ("What is Qto_beam.Missing of Beam X?", "missing"),
])
def test_structured_resolution_errors(bilingual_dataset, question, code):
    with pytest.raises(ResolutionError) as error:
        query(bilingual_dataset, question)
    assert error.value.as_dict()["code"] == code


def test_duplicate_object_name_is_ambiguous(bilingual_dataset):
    beam = next(e for e in bilingual_dataset.entities if e.kind == "beam")
    dataset = BuildingDataset((*bilingual_dataset.entities, replace(beam, entity_id="duplicate")))
    with pytest.raises(ResolutionError) as error:
        query(dataset, "Beam X 有多长？")
    assert error.value.code == "ambiguous"
    assert set(error.value.candidates) == {"beam", "duplicate"}


@pytest.mark.parametrize("alias,semantic", sorted(PROPERTY_ALIASES.items()))
def test_property_aliases_share_canonical_semantics(bilingual_dataset, alias, semantic):
    expected = query(bilingual_dataset, f"What is the {semantic} of Beam X?")
    actual = query(bilingual_dataset, f"梁 X 的{alias}？")
    assert actual.plan == expected.plan
    assert actual.answer == expected.answer


@pytest.mark.parametrize("alias", ["一层", "1层", "第一层"])
def test_first_level_aliases_use_local_resolver(bilingual_dataset, alias):
    entities = tuple(replace(e, name="Level 1") if e.kind == "storey" else e for e in bilingual_dataset.entities)
    dataset = BuildingDataset(entities)
    assert query(dataset, f"{alias}有多少门？").plan == query(dataset, "How many doors are on Level 1?").plan


def test_inherited_property_provenance_and_instance_override(tmp_path):
    model = ifcopenshell.file(schema="IFC4")
    door = model.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(), Name="Door T")
    prop = model.create_entity("IfcPropertySingleValue", Name="Length", NominalValue=model.create_entity("IfcLengthMeasure", 10.0))
    pset = model.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name="Pset_Test", HasProperties=[prop])
    door_type = model.create_entity("IfcDoorType", GlobalId=ifcopenshell.guid.new(), HasPropertySets=[pset])
    model.create_entity("IfcRelDefinesByType", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[door], RelatingType=door_type)
    path = tmp_path / "inheritance.ifc"
    model.write(str(path))
    inherited = IfcOpenShellParser().parse(path).entities[0].properties[0]
    assert inherited.inherited and inherited.source_id == prop.id()
    assert inherited.unit is None  # No project unit assignment: do not assume mm.
    local = model.create_entity("IfcPropertySingleValue", Name="Length", NominalValue=model.create_entity("IfcLengthMeasure", 20.0))
    own = model.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name="Pset_Test", HasProperties=[local])
    model.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[door], RelatingPropertyDefinition=own)
    model.write(str(path))
    entity = IfcOpenShellParser().parse(path).entities[0]
    resolved = resolve_property(entity, "length")
    assert not resolved.inherited
    assert resolved.source_id == local.id()
    assert resolved.value == entity.attributes["Pset_Test.Length"] == 20.0


def test_equal_priority_properties_are_not_silently_selected(bilingual_dataset):
    beam = next(e for e in bilingual_dataset.entities if e.kind == "beam")
    duplicate = replace(beam.properties[0], set_name="Qto_Other", value=99)
    with pytest.raises(ResolutionError) as error:
        resolve_property(replace(beam, properties=(*beam.properties, duplicate)), "length")
    assert error.value.code == "ambiguous"


@pytest.fixture
def unit_dataset(tmp_path):
    model = ifcopenshell.file(schema="IFC4")
    mm = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")
    metre = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    area = model.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")
    volume = model.create_entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
    units = model.create_entity("IfcUnitAssignment", Units=[mm, area, volume])
    model.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), UnitsInContext=units)
    beam = model.create_entity("IfcBeam", GlobalId=ifcopenshell.guid.new(), Name="Beam U")
    definitions = [
        ("Length", "IfcLengthMeasure", 12.0, None),
        ("Override", "IfcLengthMeasure", 2.0, metre),
        ("Area", "IfcAreaMeasure", 3.0, None),
        ("Volume", "IfcVolumeMeasure", 4.0, None),
        ("Count", "IfcCountMeasure", 5.0, None),
        ("Ratio", "IfcRatioMeasure", 0.5, None),
        ("Enabled", "IfcBoolean", False, None),
        ("Label", "IfcLabel", "text", None),
        ("UnmeasuredLength", "IfcReal", 7.0, None),
        ("Empty", None, None, None),
    ]
    props = [model.create_entity("IfcPropertySingleValue", Name=name,
                                 NominalValue=model.create_entity(measure, value) if measure else None, Unit=unit)
             for name, measure, value, unit in definitions]
    pset = model.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name="Pset_Test", HasProperties=props)
    model.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[beam], RelatingPropertyDefinition=pset)
    path = tmp_path / "units.ifc"
    model.write(str(path))
    return IfcOpenShellParser().parse(path)


@pytest.mark.parametrize("field,unit,measure,value", [
    ("Length", "mm", "IfcLengthMeasure", 12.0),
    ("Override", "m", "IfcLengthMeasure", 2.0),
    ("Area", "m²", "IfcAreaMeasure", 3.0),
    ("Volume", "m³", "IfcVolumeMeasure", 4.0),
    ("Count", "1", "IfcCountMeasure", 5.0),
    ("Ratio", "1", "IfcRatioMeasure", 0.5),
    ("Enabled", None, "IfcBoolean", False),
    ("Label", None, "IfcLabel", "text"),
    ("UnmeasuredLength", None, "IfcReal", 7.0),
])
def test_measure_units_and_values_are_preserved(unit_dataset, field, unit, measure, value):
    answer = query(unit_dataset, f"What is Pset_Test.{field} of Beam U?").answer
    prop = answer.evidence[0].properties[0]
    assert (prop.unit, prop.measure_type, prop.value) == (unit, measure, value)
    assert type(prop.value) is type(value)
    assert prop.source is PropertySource.PSET
    assert prop.source_id is not None
    if field == "Override":
        assert prop.unit_source == "explicit property unit"


def test_null_property_is_missing(unit_dataset):
    with pytest.raises(ResolutionError) as error:
        query(unit_dataset, "What is Pset_Test.Empty of Beam U?")
    assert error.value.code == "missing"


def test_show_properties_is_bounded_and_has_provenance(bilingual_dataset):
    beam = next(e for e in bilingual_dataset.entities if e.kind == "beam")
    beam = replace(beam, properties=tuple(replace(beam.properties[0], field_name=f"Field{i}") for i in range(50)))
    outcome = query(BuildingDataset((beam,)), "Show the properties of Beam X.")
    assert len(outcome.answer.evidence[0].properties) == 30
    assert "30 of 50" in outcome.answer.text


class Provider:
    def __init__(self, **changes):
        self.payload = {"operation": "find", "kind": "beam", "object_ref": "Beam X", "requested_property": "length", **changes}

    def complete(self, system_prompt, user_prompt):
        return json.dumps(self.payload)


def test_llm_property_uses_same_local_resolution(bilingual_dataset):
    expected = query(bilingual_dataset, "梁 X 的长度是多少？")
    actual = run_question(bilingual_dataset, "梁 X 的长度是多少？", LLMQueryPlanner(Provider()))
    assert actual.plan == expected.plan
    assert actual.answer == expected.answer


@pytest.mark.parametrize("change", [
    {"unit": "m"}, {"value": 999}, {"requested_property": "__class__.__dict__"},
    {"requested_property": "width"}, {"kind": "IfcBeam"}, {"operation": "sum"},
])
def test_llm_cannot_invent_property_value_unit_or_schema(bilingual_dataset, change):
    with pytest.raises(InvalidPlannerOutputError):
        run_question(bilingual_dataset, "What is the length of Beam X?", LLMQueryPlanner(Provider(**change)))


def test_llm_cannot_replace_object_property_with_aggregate(synthetic_dataset):
    provider = Provider()
    provider.payload = {"operation": "aggregate", "kind": "space", "aggregate_function": "max", "aggregate_field": "area"}
    with pytest.raises(InvalidPlannerOutputError, match="omitted"):
        run_question(synthetic_dataset, "What is the area of Room 101?", LLMQueryPlanner(provider))


@pytest.mark.parametrize("label,kind,set_name,field,total,unit", [
    ("rac", "door", "Qto_DoorBaseQuantities", "Width", 16, "mm"),
    ("rac", "door", "Qto_DoorBaseQuantities", "Height", 16, "mm"),
    ("rac", "door", "Qto_DoorBaseQuantities", "Area", 16, "m²"),
    ("rac", "window", "Qto_WindowBaseQuantities", "Width", 17, "mm"),
    ("rac", "window", "Qto_WindowBaseQuantities", "Height", 17, "mm"),
    ("rac", "window", "Qto_WindowBaseQuantities", "Area", 17, "m²"),
    ("rst", "beam", "Qto_BeamBaseQuantities", "Length", 370, "mm"),
    ("rst", "beam", "Qto_BeamBaseQuantities", "NetVolume", 370, "m³"),
    ("rst", "column", "Qto_ColumnBaseQuantities", "Length", 30, "mm"),
    ("rst", "column", "Qto_ColumnBaseQuantities", "NetVolume", 30, "m³"),
    ("rst", "slab", "Qto_SlabBaseQuantities", "GrossArea", 5, "m²"),
    ("rst", "slab", "Qto_SlabBaseQuantities", "NetVolume", 5, "m³"),
    ("rst", "footing", "Qto_FootingBaseQuantities", "Length", 4, "mm"),
    ("rst", "footing", "Qto_FootingBaseQuantities", "Width", 4, "mm"),
    ("rst", "pile", "Qto_PileBaseQuantities", "Length", 32, "mm"),
    ("rst", "pile", "Qto_PileBaseQuantities", "NetVolume", 32, "m³"),
])
def test_course_quantities_match_original_ifc(course_models, label, kind, set_name, field, total, unit):
    model, dataset = course_models[label]
    entities = [e for e in dataset.entities if e.kind == kind]
    assert len(entities) == total
    for entity in entities:
        plan = QueryPlan(QueryOperation.FIND, kind=kind,
                         filters=(FilterCondition("entity_id", FilterOperator.EQ, entity.entity_id),),
                         requested_property=f"{set_name}.{field}")
        result = QueryEngine().execute(plan, dataset)
        prop = result.properties[0]
        original = model.by_id(prop.source_id)
        assert result.value == original[3]
        assert prop.unit == unit
        assert prop.source is PropertySource.QUANTITY
        assert result.entities[0].global_id == model.by_id(int(entity.entity_id[4:])).GlobalId
    first = entities[0]
    outcome = query(dataset, f"What is {set_name}.{field} of {first.name}?")
    assert outcome.answer.evidence[0].properties[0].path == f"{set_name}.{field}"


def test_course_beam_example_multilingual(course_models):
    dataset = course_models["rst"][1]
    outcomes = [query(dataset, q) for q in (
        "What is the length of Beam 1046268?", "梁 1046268 的长度是多少？", "Beam 1046268 有多长？",
    )]
    assert outcomes[0].plan == outcomes[1].plan == outcomes[2].plan
    assert outcomes[0].answer == outcomes[1].answer == outcomes[2].answer
    evidence = outcomes[0].answer.evidence[0]
    assert evidence.global_id == "3zL2DJMkrEuekgiISjJ_Rg"
    assert outcomes[0].answer.value == 4242.6
    assert evidence.properties[0].path == "Qto_BeamBaseQuantities.Length"
    assert evidence.properties[0].unit == "mm"


def test_course_llm_property_is_resolved_locally(course_models):
    dataset = course_models["rst"][1]
    question = "Beam 1046268 的长度是多少？"
    actual = run_question(dataset, question, LLMQueryPlanner(Provider(object_ref="1046268")))
    assert actual.answer == query(dataset, question).answer


def test_course_show_column_properties_has_field_provenance(course_models):
    model, dataset = course_models["rst"]
    column = next(e for e in dataset.entities if e.kind == "column")
    english = query(dataset, f"Show the properties of {column.name}.")
    chinese = query(dataset, f"{column.name} 的参数？")
    assert english.plan == chinese.plan
    assert english.answer == chinese.answer
    assert 0 < len(english.result.properties) <= 30
    for p in english.result.properties:
        original = model.by_id(p.source_id)
        assert original.Name == p.field_name
        assert original[3] == p.value if p.source is PropertySource.QUANTITY else original.NominalValue.wrappedValue == p.value


def test_course_door_area_conflict_is_explicit(course_models):
    dataset = course_models["rac"][1]
    name = "Single-Flush:800 x 2100:422466"
    for question in (f"What is the area of {name}?", f"{name} 的面积是多少？"):
        with pytest.raises(ResolutionError) as error:
            query(dataset, question)
        assert error.value.code == "ambiguous"
        assert any("Dimensions.Area" in p for p in error.value.candidates)
        assert any("Qto_DoorBaseQuantities.Area" in p for p in error.value.candidates)
    assert query(dataset, f"What is Qto_DoorBaseQuantities.Area of {name}?").answer.value == pytest.approx(1.68)
    assert query(dataset, f"What is Dimensions.Area of {name}?").answer.value == pytest.approx(2.965)


@pytest.mark.parametrize("kind,semantic,missing_count", [("slab", "length", 4), ("footing", "height", 3)])
def test_course_missing_dimensions_are_not_invented(course_models, kind, semantic, missing_count):
    dataset = course_models["rst"][1]
    failures = []
    for entity in dataset.entities:
        if entity.kind != kind:
            continue
        try:
            query(dataset, f"What is the {semantic} of {entity.name}?")
        except ResolutionError as error:
            assert error.code == "missing"
            failures.append(entity.global_id)
    assert len(failures) == missing_count


def test_course_chinese_scope_preserves_phase2_semantics(course_models):
    rac = course_models["rac"][1]
    assert query(rac, "二层有多少扇门？").answer == query(rac, "How many doors are on Level 2?").answer
    rst = course_models["rst"][1]
    assert query(rst, "Reference Level 为二层的梁有多少？").answer.value == 84
    with pytest.raises(ValueError):
        query(rst, "二层有多少根梁？")


def test_evidence_panel_renders_property_fields():
    app = AppTest.from_string('''
import streamlit as st
from bim_evidence_qa.domain import BuildingDataset, BuildingEntity, PropertyValue, PropertySource
from bim_evidence_qa.application import run_question
from bim_evidence_qa.query import DevelopmentNaturalLanguagePlanner
from bim_evidence_qa.web import _render_ifc_evidence
p = PropertyValue(PropertySource.QUANTITY, "Qto_Test", "Length", 4242.6, "IfcLengthMeasure", "mm", 1)
e = BuildingEntity("b", "beam", "Beam X", "G-BEAM", properties=(p,))
outcome = run_question(BuildingDataset((e,)), "梁 X 的长度是多少？", DevelopmentNaturalLanguagePlanner())
_render_ifc_evidence("en", outcome)
''').run(timeout=15)
    assert not app.exception
    table = app.dataframe[0].value
    assert table.iloc[0]["Unit"] == "mm"
    assert table.iloc[0]["Set"] == "Qto_Test"
    assert table.iloc[0]["Value"] == "4242.6"
