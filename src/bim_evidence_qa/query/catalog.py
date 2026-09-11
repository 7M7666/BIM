from dataclasses import dataclass, field
from typing import Mapping

from bim_evidence_qa.domain import (
    AggregateFunction,
    BuildingDataset,
    BuildingEntity,
    QueryOperation,
    FilterCondition,
    FilterOperator,
)


REFERENCE_LEVEL_FIELD = "Constraints.Reference Level"


class LevelResolutionError(ValueError):
    """A requested level is absent or ambiguous in the current dataset."""


def normalize_level_name(value: str) -> str:
    return " ".join(value.casefold().split())


@dataclass(frozen=True, slots=True)
class QueryCatalog:
    kinds: frozenset[str]
    attributes: frozenset[str]
    attributes_by_kind: Mapping[str, frozenset[str]]
    entity_names: frozenset[str]
    container_ids: frozenset[str]
    container_names: frozenset[str]
    operations: frozenset[QueryOperation]
    storeys_by_id: Mapping[str, str | None] = field(default_factory=dict)
    reference_levels_by_kind: Mapping[str, frozenset[str]] = field(default_factory=dict)
    entities_by_id: Mapping[str, BuildingEntity] = field(default_factory=dict)

    def resolve_level(self, name: str, *, reference: bool = False,
                      kind: str | None = None) -> FilterCondition:
        normalized = normalize_level_name(name)
        if reference:
            candidates = [
                value for value in sorted(self.reference_levels_by_kind.get(kind, ()))
                if normalize_level_name(value) == normalized
            ]
            field_name = REFERENCE_LEVEL_FIELD
            label = "Reference Level property"
        else:
            candidates = [
                entity_id for entity_id, value in self.storeys_by_id.items()
                if value is not None and normalize_level_name(value) == normalized
            ]
            field_name = "container_id"
            label = "IfcBuildingStorey"
        if not candidates:
            raise LevelResolutionError(f"{label} '{name}' is unavailable (not found).")
        if len(candidates) != 1:
            raise LevelResolutionError(f"Ambiguous {label} '{name}': multiple matches.")
        return FilterCondition(field_name, FilterOperator.EQ, candidates[0])

    def supports_attribute(self, kind: str, attribute: str) -> bool:
        return attribute in self.attributes_by_kind.get(kind, frozenset())

    def as_prompt_payload(self) -> dict[str, object]:
        return {
            "kinds": sorted(self.kinds),
            "attributes_by_kind": {
                kind: sorted(attributes)
                for kind, attributes in sorted(self.attributes_by_kind.items())
            },
            "entity_names": sorted(self.entity_names),
            "container_ids": sorted(self.container_ids),
            "container_names": sorted(self.container_names),
            "storeys_by_id": dict(self.storeys_by_id),
            "reference_levels_by_kind": {
                kind: sorted(values) for kind, values in sorted(self.reference_levels_by_kind.items())
            },
            "operations": sorted(operation.value for operation in self.operations),
            "aggregate_functions": sorted(
                function.value for function in AggregateFunction
            ),
        }

    @classmethod
    def from_dataset(cls, dataset: BuildingDataset) -> "QueryCatalog":
        entities_by_id = {entity.entity_id: entity for entity in dataset.entities}
        storeys = tuple(entity for entity in dataset.entities if entity.kind == "storey")
        referenced_container_ids = {
            entity.container_id
            for entity in dataset.entities
            if entity.container_id is not None
        }
        container_ids = referenced_container_ids | {
            storey.entity_id for storey in storeys
        }
        container_names = {
            entity.name
            for container_id in container_ids
            if (entity := entities_by_id.get(container_id)) is not None
            and entity.name is not None
        }

        return cls(
            kinds=frozenset(entity.kind for entity in dataset.entities),
            attributes=frozenset(
                attribute
                for entity in dataset.entities
                for attribute in entity.attributes
            ),
            attributes_by_kind={
                kind: frozenset(
                    attribute
                    for entity in dataset.entities
                    if entity.kind == kind
                    for attribute in entity.attributes
                )
                for kind in {entity.kind for entity in dataset.entities}
            },
            entity_names=frozenset(
                entity.name for entity in dataset.entities if entity.name is not None
            ),
            container_ids=frozenset(container_ids),
            container_names=frozenset(container_names),
            operations=frozenset(QueryOperation),
            entities_by_id=entities_by_id,
            storeys_by_id={storey.entity_id: storey.name for storey in storeys},
            reference_levels_by_kind={
                kind: frozenset(
                    value for entity in dataset.entities if entity.kind == kind
                    if isinstance(value := entity.attributes.get(REFERENCE_LEVEL_FIELD), str)
                    and value.strip()
                )
                for kind in {entity.kind for entity in dataset.entities}
            },
        )
