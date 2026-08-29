from pathlib import Path

import pytest

from bim_evidence_qa.domain import BuildingDataset
from bim_evidence_qa.parsers import IfcOpenShellParser, SyntheticFixtureParser


@pytest.fixture
def synthetic_fixture_path() -> Path:
    return Path(__file__).parent / "fixtures" / "synthetic_project.json"


@pytest.fixture
def synthetic_dataset(synthetic_fixture_path: Path) -> BuildingDataset:
    return SyntheticFixtureParser().parse(synthetic_fixture_path)


@pytest.fixture
def development_ifc_path() -> Path:
    return Path(__file__).parent / "fixtures" / "development_only_minimal.ifc"


@pytest.fixture
def development_ifc_dataset(development_ifc_path: Path) -> BuildingDataset:
    return IfcOpenShellParser().parse(development_ifc_path)
