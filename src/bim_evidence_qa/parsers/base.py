from pathlib import Path
from typing import Protocol

from bim_evidence_qa.domain import BuildingDataset


class DatasetParser(Protocol):
    def parse(self, path: Path) -> BuildingDataset:
        """Parse one input file into the normalized building dataset."""

        ...
