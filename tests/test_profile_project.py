import hashlib

import pymupdf

from bim_evidence_qa.profile_project import profile_ifc, profile_pdf


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ifc_profiler_is_read_only(development_ifc_path):
    before = _digest(development_ifc_path)

    profile_ifc(development_ifc_path)

    assert _digest(development_ifc_path) == before


def test_ifc_profiler_finds_real_entity_types(development_ifc_path):
    profile = profile_ifc(development_ifc_path)

    assert profile["schema"] == "IFC4"
    assert profile["entity_types"]["IfcBuildingStorey"]["count"] == 2
    assert profile["entity_types"]["IfcSpace"]["count"] == 3
    assert profile["entity_types"]["IfcDoor"]["count"] == 2
    assert profile["entity_types"]["IfcWindow"]["count"] == 1
    assert profile["entity_types"]["IfcWall"]["count"] == 1
    assert profile["entity_types"]["IfcSpace"]["without_name"] == 1


def test_ifc_profiler_discovers_real_psets_and_quantities(development_ifc_path):
    profile = profile_ifc(development_ifc_path)

    assert profile["property_sets"] == ["DevelopmentDoorProperties"]
    assert profile["quantities"] == ["DevelopmentSpaceQuantities"]
    assert profile["discoveries_by_entity_type"]["IfcDoor"][
        "property_sets"
    ] == ["DevelopmentDoorProperties"]
    assert profile["discoveries_by_entity_type"]["IfcSpace"][
        "quantities"
    ] == ["DevelopmentSpaceQuantities"]
    assert profile["attributes_by_entity_kind"]["space"] == [
        "DevelopmentSpaceQuantities.MeasuredArea"
    ]


def test_ifc_profiler_inventory_reports_relation_types(development_ifc_path):
    profile = profile_ifc(development_ifc_path)

    assert profile["relations"]["IfcRelAggregates"]["count"] == 3
    assert (
        profile["relations"]["IfcRelContainedInSpatialStructure"]["count"]
        == 2
    )
    assert "IfcSpace" in profile["relations"]["IfcRelAggregates"][
        "related_entity_types"
    ]


def test_pdf_profiler_reports_text_and_blank_pages_without_modifying_file(
    tmp_path,
):
    path = tmp_path / "mixed.pdf"
    document = pymupdf.open()
    document.set_metadata({"title": "Profiler Drawing"})
    page = document.new_page()
    page.insert_text((72, 72), "Room 101 floor plan")
    document.new_page()
    document.save(path)
    document.close()
    before = _digest(path)

    profile = profile_pdf(path)

    assert profile["pages"] == 2
    assert profile["pages_with_text"] == 1
    assert profile["pages_without_text"] == 1
    assert profile["total_extracted_characters"] > 0
    assert profile["metadata"]["title"] == "Profiler Drawing"
    assert profile["page_text_samples"][0]["text"] == "Room 101 floor plan"
    assert profile["page_text_samples"][1]["text"] == ""
    assert _digest(path) == before
