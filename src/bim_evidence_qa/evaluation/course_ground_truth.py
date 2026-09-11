"""Author/verify the frozen course cases directly from IFC, never from QA outputs."""

import argparse
import hashlib
import json
from pathlib import Path

import ifcopenshell
from ifcopenshell.util.element import get_container, get_psets


def build_cases(folder: Path) -> list[dict]:
    models = {key: ifcopenshell.open(str(folder / f"{key}_basic_sample_project.ifc")) for key in ("rac", "rst")}
    hashes = {key: hashlib.sha256((folder / f"{key}_basic_sample_project.ifc").read_bytes()).hexdigest() for key in models}
    cases = []

    def add(key, question, language, category, kind, objects=(), operation="count", status="success",
            value=None, scope=(), requested=None, prop=None, candidates=(), targeted=False, note=""):
        objects = tuple(objects)
        if operation == "count" and status == "success":
            value = len(objects)
        cases.append({
            "id": f"course-{len(cases)+1:02d}", "question": question, "language": language,
            "model": key, "category": category, "expected_status": status,
            "expected_operation": operation, "expected_entity_type": kind,
            "expected_scope": list(scope), "requested_property": requested,
            "expected_value": value, "expected_unit": prop["unit"] if prop else None,
            "expected_entity_ids": [f"ifc-{e.id()}" for e in objects] if status == "success" else [],
            "expected_global_ids": [e.GlobalId for e in objects] if status == "success" else [],
            "expected_object_ids": [f"ifc-{e.id()}" for e in objects] if targeted else [],
            "expected_property_source": {k: v for k, v in prop.items() if k != "unit"} if prop else None,
            "expected_candidates": list(candidates),
            "notes": f"IFC SHA256 {hashes[key]}. {note}",
        })

    count_specs = [
        ("rac", "door", "有多少扇门？", "zh"), ("rac", "window", "How many windows are there?", "en"),
        ("rac", "wall", "墙体的数量？", "zh"), ("rac", "column", "How many columns are there?", "en"),
        ("rac", "slab", "有多少楼板？", "zh"), ("rac", "pile", "How many piles are there?", "en"),
        ("rst", "beam", "有多少根梁？", "zh"), ("rst", "column", "How many columns are there?", "en"),
        ("rst", "slab", "有多少 slabs？", "mixed"), ("rst", "footing", "How many footings are there?", "en"),
        ("rst", "pile", "桩基的数量？", "zh"), ("rac", "storey", "How many storeys are there?", "en"),
        ("rst", "space", "How many spaces are there?", "en"),
    ]
    types = {kind: "Ifc" + kind.title() for _, kind, _, _ in count_specs}
    types["storey"] = "IfcBuildingStorey"
    for key, kind, question, language in count_specs:
        add(key, question, language, "count", kind, models[key].by_type(types[kind]), note=f"Count model.by_type('{types[kind]}'), including subclasses.")
    for key, kind, question, language in [
        ("rac", "door", "列出所有门。", "zh"), ("rac", "window", "List all windows.", "en"),
        ("rst", "beam", "List all beams.", "en"), ("rst", "slab", "显示所有楼板。", "zh"),
        ("rst", "pile", "List all piles.", "en"),
    ]:
        add(key, question, language, "list", kind, models[key].by_type(types[kind]), operation="find", note="Compare complete IFC GlobalId set; order is not significant.")
    door = next(e for e in models["rac"].by_type("IfcDoor") if e.Name.endswith(":422466"))
    beam = next(e for e in models["rst"].by_type("IfcBeam") if e.Name.endswith(":1046268"))
    column = models["rst"].by_type("IfcColumn")[0]
    window = models["rac"].by_type("IfcWindow")[0]
    for key, kind, entity, question, lang in [
        ("rac", "door", door, f"Find {door.Name}", "en"),
        ("rst", "beam", beam, "Find beam 1046268", "en"),
        ("rst", "column", column, f"Find {column.GlobalId}", "en"),
    ]:
        add(key, question, lang, "find", kind, [entity], operation="find", targeted=True, note="Exact name, exported element number, or GlobalId; one verified IFC entity.")
    for level, question in [("Level 1", "一层有多少门？"), ("Level 1 Living Rm.", "How many doors are on Level 1 Living Rm.?"), ("Level 2", "Level 2 有多少门？")]:
        storey = next(e for e in models["rac"].by_type("IfcBuildingStorey") if e.Name == level)
        objects = [e for e in models["rac"].by_type("IfcDoor") if get_container(e) == storey]
        add("rac", question, "en" if question.startswith("How") else "mixed", "spatial_scope", "door", objects,
            scope=[{"field": "container_id", "operator": "eq", "value": f"ifc-{storey.id()}"}],
            note=f"Actual IfcBuildingStorey {storey.GlobalId} ({level}); follow IFC containment/decomposition, including curtain-wall doors.")
    for level, question, lang in [("Level 2", "Reference Level 为 Level 2 的梁有多少？", "mixed"), ("Foundation", "How many beams have Reference Level Foundation?", "en"), ("Level Lower", "How many beams have Reference Level Level Lower?", "en")]:
        objects = [e for e in models["rst"].by_type("IfcBeam") if get_psets(e)["Constraints"]["Reference Level"] == level]
        add("rst", question, lang, "reference_level", "beam", objects,
            scope=[{"field": "Constraints.Reference Level", "operator": "eq", "value": level}], note="Property-based Reference Level only; RST has no IfcBuildingStorey.")

    slab = models["rst"].by_type("IfcSlab")[0]
    footings = models["rst"].by_type("IfcFooting")
    footing = next((e for e in footings if e.Name.endswith(":1178029")), footings[0])
    piles = models["rst"].by_type("IfcPile")
    pile = next((e for e in piles if e.Name.endswith(":1175183")), piles[0])
    specs = [
        ("rst", "beam", beam, "Length", "length", "梁 1046268 的长度是多少？", "mixed"),
        ("rst", "beam", beam, "NetVolume", "volume", "What is the volume of Beam 1046268?", "en"),
        ("rst", "column", column, "Length", "length", f"{column.Name} 的长度是多少？", "mixed"),
        ("rst", "slab", slab, "GrossArea", None, None, "en"),
        ("rst", "slab", slab, "NetVolume", "volume", f"{slab.Name} 的体积？", "mixed"),
        ("rst", "footing", footing, "Width", "width", f"What is the width of {footing.Name}?", "en"),
        ("rst", "pile", pile, "Length", "length", f"{pile.Name} 的长度？", "mixed"),
        ("rac", "door", door, "Width", "width", f"{door.Name} 的宽度是多少？", "mixed"),
        ("rac", "door", door, "Height", "height", f"What is the height of {door.Name}?", "en"),
        ("rac", "window", window, "Width", "width", f"What is the width of {window.Name}?", "en"),
        ("rac", "door", door, "Area", None, None, "en"),
        ("rac", "window", window, "Area", None, None, "en"),
    ]
    for key, kind, entity, field, semantic, question, lang in specs:
        set_name = f"Qto_{kind.title()}BaseQuantities"
        raw = get_psets(entity, qtos_only=True, verbose=True)[set_name][field]
        prop = models[key].by_id(raw["id"])
        measure = prop.wrapped_data.declaration().as_entity().attribute_by_index(3).type_of_attribute().declared_type().name()
        unit = {"IfcLengthMeasure": "mm", "IfcAreaMeasure": "m²", "IfcVolumeMeasure": "m³"}[measure]
        path = f"{set_name}.{field}"
        add(key, question or f"What is {path} of {entity.Name}?", lang, "property", kind, [entity], operation="find",
            value=raw["value"], requested=semantic or path, targeted=True,
            prop={"path": path, "source": "Quantity Set", "set_name": set_name, "field_name": field, "measure_type": measure, "unit": unit},
            note=f"Read raw IFC quantity #{prop.id()}, {path}. Units confirmed from supplied IFC project SI assignment; no QA resolver used.")
    for kind, field in [("slab", "Length"), ("footing", "Height")]:
        entity = next(e for e in models["rst"].by_type(types[kind]) if not any(field in values for values in get_psets(e).values()))
        add("rst", f"What is the {field.lower()} of {entity.Name}?", "en", "missing", kind, [entity], operation="find", status="missing", requested=field.lower(), targeted=True, note=f"Raw Psets and Qtos have no {field}; do not infer geometry.")
    add("rac", f"{door.Name} 这个门的面积是多少？", "mixed", "ambiguous", "door", [door], operation="find", status="ambiguous", requested="area", targeted=True,
        candidates=["Dimensions.Area", "Qto_DoorBaseQuantities.Area"], note="Explicit object provided (no conversation memory). Raw Dimensions.Area ~=2.965 vs Qto Area ~=1.68.")
    for key, question, language, note in [
        ("rst", "Which IfcBuildingStorey contains these beams?", "en", "No IfcBuildingStorey exists; relationship operation unsupported."),
        ("rac", "Which doors intersect a wall geometrically?", "en", "Geometry inference is not implemented."),
        ("rst", "What is the construction cost of this building?", "en", "No supported cost calculation or pricing data."),
        ("rac", "电梯的数量是多少？", "zh", "Elevator entity concept is unsupported."),
        ("rac", "这个门的宽度是多少？", "zh", "No object identified; conversation memory intentionally absent."),
    ]:
        add(key, question, language, "unsupported", None, operation=None, status="unsupported", note=note)
    add("rst", "What is the length of Beam NO-SUCH-OBJECT?", "en", "entity_not_found", "beam", operation=None, status="entity_not_found", requested="length", note="Identifier absent from raw IFC names, IDs and GlobalIds.")
    assert 40 <= len(cases) <= 60
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path, default=Path("tests/fixtures/course_cases.json"))
    parser.add_argument("--write", action="store_true", help="Explicitly author the frozen cases; default only verifies them")
    args = parser.parse_args()
    cases = build_cases(args.folder)
    if args.write:
        args.output.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        assert cases == json.loads(args.output.read_text(encoding="utf-8")), "Ground truth differs from raw IFC; do not overwrite to fit QA output"
    print(f"{'Wrote' if args.write else 'Verified'} {len(cases)} raw-IFC course cases")


if __name__ == "__main__":
    main()
