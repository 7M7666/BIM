import json
from pathlib import Path

import pytest

from bim_evidence_qa.domain import BuildingDataset, BuildingEntity


@pytest.fixture
def synthetic_dataset() -> BuildingDataset:
    fixture_path = Path(__file__).parent / "fixtures" / "synthetic_project.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert payload["fixture_type"] == "synthetic-development-only"
    assert payload["allowed_for_accuracy_evaluation"] is False

    entities = tuple(
        BuildingEntity(
            entity_id=item["entity_id"],
            kind=item["kind"],
            name=item["name"],
            global_id=item["global_id"],
            container_id=item["container_id"],
            attributes=item["attributes"],
        )
        for item in payload["entities"]
    )
    return BuildingDataset(entities=entities)
