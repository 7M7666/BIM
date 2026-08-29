from pathlib import Path

import ifcopenshell
from ifcopenshell.util.element import get_psets

from bim_evidence_qa.domain import BuildingDataset, BuildingEntity, ScalarValue


class IFCParseError(ValueError):
    """Raised when an IFC file cannot be opened or normalized."""


class IfcOpenShellParser:
    _ENTITY_TYPES = {
        "IfcBuildingStorey": "storey",
        "IfcSpace": "space",
        "IfcDoor": "door",
        "IfcWindow": "window",
        "IfcWall": "wall",
    }

    def parse(self, path: Path) -> BuildingDataset:
        try:
            model = ifcopenshell.open(str(path))
            entities = tuple(
                self._normalize(entity, kind)
                for ifc_type, kind in self._ENTITY_TYPES.items()
                for entity in sorted(model.by_type(ifc_type), key=lambda item: item.id())
            )
            return BuildingDataset(entities=entities)
        except (ifcopenshell.Error, OSError, RuntimeError, ValueError) as error:
            raise IFCParseError(f"Cannot parse IFC '{path}': {error}") from error

    def _normalize(self, entity, kind: str) -> BuildingEntity:
        return BuildingEntity(
            entity_id=self._entity_id(entity),
            kind=kind,
            name=self._optional_text(getattr(entity, "Name", None)),
            global_id=self._optional_text(getattr(entity, "GlobalId", None)),
            container_id=self._container_id(entity),
            attributes=self._attributes(entity),
        )

    def _container_id(self, entity) -> str | None:
        contained_relations = sorted(
            getattr(entity, "ContainedInStructure", ()) or (),
            key=lambda relation: relation.id(),
        )
        for relation in contained_relations:
            container = getattr(relation, "RelatingStructure", None)
            if container is not None:
                return self._entity_id(container)

        decomposition_relations = sorted(
            getattr(entity, "Decomposes", ()) or (),
            key=lambda relation: relation.id(),
        )
        for relation in decomposition_relations:
            if not relation.is_a("IfcRelAggregates"):
                continue
            container = getattr(relation, "RelatingObject", None)
            if container is not None:
                return self._entity_id(container)
        return None

    def _attributes(self, entity) -> dict[str, ScalarValue]:
        attributes: dict[str, ScalarValue] = {}
        for values in (
            get_psets(entity, psets_only=True),
            get_psets(entity, qtos_only=True),
        ):
            for set_name in sorted(values):
                set_values = values[set_name]
                if not isinstance(set_values, dict):
                    continue
                for property_name in sorted(set_values):
                    if property_name == "id":
                        continue
                    value = set_values[property_name]
                    if self._is_scalar(value):
                        attributes[f"{set_name}.{property_name}"] = value
        return attributes

    @staticmethod
    def _entity_id(entity) -> str:
        return f"ifc-{entity.id()}"

    @staticmethod
    def _optional_text(value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _is_scalar(value: object) -> bool:
        return value is None or isinstance(value, (str, int, float, bool))
