from pathlib import Path
from collections import deque

import ifcopenshell
from ifcopenshell.util.element import get_psets, get_type
from ifcopenshell.util.unit import get_property_unit, get_unit_symbol

from bim_evidence_qa.domain import BuildingDataset, BuildingEntity, ScalarValue, PropertySource, PropertyValue


class IFCParseError(ValueError):
    """Raised when an IFC file cannot be opened or normalized."""


class IfcOpenShellParser:
    _ENTITY_TYPES = {
        "IfcBuildingStorey": "storey",
        "IfcSpace": "space",
        "IfcDoor": "door",
        "IfcWindow": "window",
        "IfcWall": "wall",
        "IfcBeam": "beam",
        "IfcColumn": "column",
        "IfcSlab": "slab",
        "IfcFooting": "footing",
        "IfcPile": "pile",
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
            properties=self._properties(entity),
        )

    def _properties(self, entity) -> tuple[PropertyValue, ...]:
        has_project = bool(entity.file.by_type("IfcProject"))
        element_type = get_type(entity)
        inherited_sets = getattr(element_type, "HasPropertySets", ()) or ()
        own_sets = [
            rel.RelatingPropertyDefinition for rel in getattr(entity, "IsDefinedBy", ()) or ()
            if rel.is_a("IfcRelDefinesByProperties")
        ]
        records = []
        for inherited, definitions in ((True, inherited_sets), (False, own_sets)):
            current = []
            for definition in definitions:
                if definition.is_a("IfcPropertySet"):
                    fields, source = definition.HasProperties, PropertySource.PSET
                elif definition.is_a("IfcElementQuantity"):
                    fields, source = definition.Quantities, PropertySource.QUANTITY
                else:
                    continue
                for prop in fields or ():
                    measure = None
                    if prop.is_a("IfcPropertySingleValue"):
                        nominal = prop.NominalValue
                        value = nominal.wrappedValue if nominal is not None else None
                        measure = nominal.is_a() if nominal is not None else None
                    elif prop.is_a("IfcPhysicalSimpleQuantity"):
                        value = prop[3]
                        declaration = prop.wrapped_data.declaration().as_entity()
                        measure = declaration.attribute_by_index(3).type_of_attribute().declared_type().name()
                    else:
                        continue
                    if not self._is_scalar(value):
                        continue
                    unit = getattr(prop, "Unit", None)
                    if unit is None and measure and has_project:
                        unit = get_property_unit(prop, entity.file)
                    symbol = None
                    unit_source = None
                    if unit is not None:
                        symbol = get_unit_symbol(unit) if getattr(unit, "Name", None) else None
                        if symbol == "?":
                            symbol = None
                        if symbol:
                            symbol = symbol.replace("2", "²").replace("3", "³")
                        unit_source = "explicit property unit" if getattr(prop, "Unit", None) else "project unit assignment"
                    elif measure in {"IfcCountMeasure", "IfcRatioMeasure", "IfcPositiveRatioMeasure", "IfcNormalisedRatioMeasure"}:
                        symbol, unit_source = "1", "dimensionless measure"
                    current.append(PropertyValue(
                        source, definition.Name or "", prop.Name or "", value,
                        measure, symbol, prop.id(), unit_source, inherited,
                    ))
            if not inherited:
                overrides = {(p.source, p.path) for p in current}
                records = [p for p in records if (p.source, p.path) not in overrides]
            records.extend(current)
        return tuple(sorted(records, key=lambda p: (p.source.value, p.path, p.source_id or 0)))

    def _container_id(self, entity) -> str | None:
        pending = deque([(entity, 0)])
        visited = {entity.id()}
        spatial = {}
        storeys = {}
        while pending:
            current, depth = pending.popleft()
            parents = [
                relation.RelatingStructure
                for relation in getattr(current, "ContainedInStructure", ()) or ()
            ]
            for relation in (
                *(getattr(current, "Decomposes", ()) or ()),
                *(getattr(current, "Nests", ()) or ()),
            ):
                if relation.is_a("IfcRelAggregates") or relation.is_a("IfcRelNests"):
                    parents.append(relation.RelatingObject)
            for parent in parents:
                if parent is None or parent.id() in visited:
                    continue
                visited.add(parent.id())
                if parent.is_a("IfcBuildingStorey"):
                    storeys[parent.id()] = parent
                    continue
                if parent.is_a("IfcSpatialStructureElement"):
                    spatial[parent.id()] = (parent, depth + 1)
                pending.append((parent, depth + 1))
        # Conflicting storeys must not be resolved by relationship iteration order.
        candidates = storeys
        if not candidates and spatial:
            nearest = min(depth for _, depth in spatial.values())
            candidates = {key: parent for key, (parent, depth) in spatial.items() if depth == nearest}
        if len(candidates) == 1:
            return self._entity_id(next(iter(candidates.values())))
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
