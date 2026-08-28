from pathlib import Path

import pytest

from bim_evidence_qa.domain import BuildingDataset
from bim_evidence_qa.parsers import SyntheticFixtureParser


@pytest.fixture
def synthetic_fixture_path() -> Path:
    return Path(__file__).parent / "fixtures" / "synthetic_project.json"


@pytest.fixture
def synthetic_dataset(synthetic_fixture_path: Path) -> BuildingDataset:
    return SyntheticFixtureParser().parse(synthetic_fixture_path)
