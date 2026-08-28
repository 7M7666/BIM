from dataclasses import dataclass

from bim_evidence_qa.domain import BuildingDataset, QueryOperation


@dataclass(frozen=True, slots=True)
class QueryCatalog:
    kinds: frozenset[str]
    attributes: frozenset[str]
    entity_names: frozenset[str]
    container_ids: frozenset[str]
    container_names: frozenset[str]
    operations: frozenset[QueryOperation]

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
            entity_names=frozenset(
                entity.name for entity in dataset.entities if entity.name is not None
            ),
            container_ids=frozenset(container_ids),
            container_names=frozenset(container_names),
            operations=frozenset(QueryOperation),
        )
