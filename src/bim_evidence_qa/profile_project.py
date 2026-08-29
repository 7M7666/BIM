import argparse
import json
from pathlib import Path
from typing import Sequence

import ifcopenshell
from ifcopenshell.util.element import get_psets

from bim_evidence_qa.parsers import IfcOpenShellParser, PyMuPDFParser


IFC_ENTITY_TYPES = (
    "IfcBuildingStorey",
    "IfcSpace",
    "IfcDoor",
    "IfcWindow",
    "IfcWall",
)
KIND_BY_IFC_TYPE = {
    "IfcBuildingStorey": "storey",
    "IfcSpace": "space",
    "IfcDoor": "door",
    "IfcWindow": "window",
    "IfcWall": "wall",
}


def profile_ifc(path: Path) -> dict[str, object]:
    model = ifcopenshell.open(str(path))
    dataset = IfcOpenShellParser().parse(path)
    normalized_by_id = {
        int(entity.entity_id.removeprefix("ifc-")): entity
        for entity in dataset.entities
    }

    entity_types = {}
    property_sets: set[str] = set()
    quantities: set[str] = set()
    discoveries_by_type = {}
    attributes_by_kind = {}

    for ifc_type in IFC_ENTITY_TYPES:
        entities = tuple(model.by_type(ifc_type))
        normalized = tuple(normalized_by_id[entity.id()] for entity in entities)
        entity_types[ifc_type] = {
            "count": len(entities),
            "with_name": sum(entity.name is not None for entity in normalized),
            "without_name": sum(entity.name is None for entity in normalized),
            "with_global_id": sum(
                entity.global_id is not None for entity in normalized
            ),
            "without_global_id": sum(
                entity.global_id is None for entity in normalized
            ),
            "with_container": sum(
                entity.container_id is not None for entity in normalized
            ),
            "without_container": sum(
                entity.container_id is None for entity in normalized
            ),
        }

        type_psets: set[str] = set()
        type_quantities: set[str] = set()
        for entity in entities:
            type_psets.update(get_psets(entity, psets_only=True))
            type_quantities.update(get_psets(entity, qtos_only=True))
        property_sets.update(type_psets)
        quantities.update(type_quantities)
        discoveries_by_type[ifc_type] = {
            "property_sets": sorted(type_psets),
            "quantities": sorted(type_quantities),
        }

        kind = KIND_BY_IFC_TYPE[ifc_type]
        attributes_by_kind[kind] = sorted(
            {
                attribute
                for entity in normalized
                for attribute in entity.attributes
            }
        )

    relations = {}
    for relation in model.by_type("IfcRelationship"):
        relation_type = relation.is_a()
        entry = relations.setdefault(
            relation_type,
            {"count": 0, "related_entity_types": set()},
        )
        entry["count"] += 1
        entry["related_entity_types"].update(_related_entity_types(relation))

    relation_payload = {
        relation_type: {
            "count": values["count"],
            "related_entity_types": sorted(values["related_entity_types"]),
        }
        for relation_type, values in sorted(relations.items())
    }

    return {
        "profile_type": "ifc",
        "file": path.name,
        "schema": model.schema,
        "entity_types": entity_types,
        "property_sets": sorted(property_sets),
        "quantities": sorted(quantities),
        "discoveries_by_entity_type": discoveries_by_type,
        "attributes_by_entity_kind": attributes_by_kind,
        "relations": relation_payload,
    }


def profile_pdf(path: Path, *, sample_length: int = 160) -> dict[str, object]:
    drawing = PyMuPDFParser().parse(path)
    pages_with_text = sum(bool(page.text.strip()) for page in drawing.pages)
    return {
        "profile_type": "pdf",
        "file": drawing.file_name,
        "pages": drawing.page_count,
        "pages_with_text": pages_with_text,
        "pages_without_text": drawing.page_count - pages_with_text,
        "total_extracted_characters": sum(len(page.text) for page in drawing.pages),
        "metadata": dict(drawing.metadata),
        "page_text_samples": [
            {
                "page_number": page.page_number,
                "text": " ".join(page.text.split())[:sample_length],
            }
            for page in drawing.pages
        ],
    }


def profile_path(path: Path) -> dict[str, object]:
    suffix = path.suffix.casefold()
    if suffix == ".ifc":
        return profile_ifc(path)
    if suffix == ".pdf":
        return profile_pdf(path)
    raise ValueError(f"Unsupported project file type: {path.suffix or '<none>'}")


def format_profile(profile: dict[str, object]) -> str:
    if profile["profile_type"] == "ifc":
        return _format_ifc_profile(profile)
    return _format_pdf_profile(profile)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only profiler for IFC and PDF project files."
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    arguments = parser.parse_args(argv)

    profiles = [profile_path(path) for path in arguments.paths]
    if arguments.as_json:
        payload = profiles[0] if len(profiles) == 1 else profiles
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print("\n\n".join(format_profile(profile) for profile in profiles))
    return 0


def _related_entity_types(relation) -> set[str]:
    related_types = set()
    for index in range(len(relation)):
        value = relation[index]
        if isinstance(value, ifcopenshell.entity_instance):
            related_types.add(value.is_a())
        elif isinstance(value, (list, tuple)):
            related_types.update(
                item.is_a()
                for item in value
                if isinstance(item, ifcopenshell.entity_instance)
            )
    return related_types


def _format_ifc_profile(profile: dict[str, object]) -> str:
    lines = [
        "IFC PROJECT PROFILE",
        f"File: {profile['file']}",
        f"IFC schema: {profile['schema']}",
        "",
        "Entity completeness:",
    ]
    for ifc_type, stats in profile["entity_types"].items():
        lines.append(
            f"- {ifc_type}: {stats['count']} | "
            f"Name {stats['with_name']}/{stats['count']} | "
            f"GlobalId {stats['with_global_id']}/{stats['count']} | "
            f"container {stats['with_container']}/{stats['count']}"
        )

    lines.extend(["", "Discovered PropertySets:"])
    lines.extend(_list_or_none(profile["property_sets"]))
    lines.extend(["", "Discovered Quantities:"])
    lines.extend(_list_or_none(profile["quantities"]))
    lines.extend(["", "Discoveries by entity type:"])
    for ifc_type, discoveries in profile["discoveries_by_entity_type"].items():
        lines.append(f"{ifc_type}")
        lines.append(
            "  Psets: " + ", ".join(discoveries["property_sets"])
            if discoveries["property_sets"]
            else "  Psets: none"
        )
        lines.append(
            "  Quantities: " + ", ".join(discoveries["quantities"])
            if discoveries["quantities"]
            else "  Quantities: none"
        )

    lines.extend(["", "Attributes by entity kind:"])
    for kind, attributes in profile["attributes_by_entity_kind"].items():
        lines.append(f"- {kind}: {', '.join(attributes) if attributes else 'none'}")

    lines.extend(["", "Relationship inventory:"])
    for relation_type, values in profile["relations"].items():
        related = ", ".join(values["related_entity_types"]) or "none"
        lines.append(f"- {relation_type}: {values['count']} | types: {related}")
    if not profile["relations"]:
        lines.append("none")
    return "\n".join(lines)


def _format_pdf_profile(profile: dict[str, object]) -> str:
    lines = [
        "PDF PROJECT PROFILE",
        f"File: {profile['file']}",
        f"Pages: {profile['pages']}",
        f"Pages with text: {profile['pages_with_text']}",
        f"Pages without text: {profile['pages_without_text']}",
        f"Total extracted characters: {profile['total_extracted_characters']}",
        f"Metadata: {json.dumps(profile['metadata'], ensure_ascii=False)}",
        "Page text samples:",
    ]
    for sample in profile["page_text_samples"]:
        text = sample["text"] or "<no extractable text>"
        lines.append(f"- page {sample['page_number']}: {text}")
    return "\n".join(lines)


def _list_or_none(values) -> list[str]:
    return [f"- {value}" for value in values] if values else ["none"]


if __name__ == "__main__":
    raise SystemExit(main())
