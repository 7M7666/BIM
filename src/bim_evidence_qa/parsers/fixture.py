import json
from json import JSONDecodeError
from pathlib import Path

from bim_evidence_qa.domain import BuildingDataset, BuildingEntity, ScalarValue


class FixtureParseError(ValueError):
    """Raised when a development fixture is invalid or unsafe to use."""


class SyntheticFixtureParser:
    FIXTURE_TYPE = "synthetic-development-only"

    def parse(self, path: Path) -> BuildingDataset:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise FixtureParseError(f"Cannot read fixture '{path}': {error}") from error
        except JSONDecodeError as error:
            raise FixtureParseError(
                f"Malformed fixture JSON in '{path}': {error.msg}."
            ) from error

        if not isinstance(payload, dict):
            raise FixtureParseError("Malformed fixture: top-level value must be an object.")
        if payload.get("fixture_type") != self.FIXTURE_TYPE:
            raise FixtureParseError(
                "Fixture rejected: fixture_type must be "
                f"'{self.FIXTURE_TYPE}'."
            )
        if payload.get("allowed_for_evaluation") is not False:
            raise FixtureParseError(
                "Fixture rejected: allowed_for_evaluation must be false."
            )

        raw_entities = payload.get("entities")
        if not isinstance(raw_entities, list):
            raise FixtureParseError("Malformed fixture: 'entities' must be a list.")

        entities = tuple(
            self._parse_entity(raw_entity, index)
            for index, raw_entity in enumerate(raw_entities)
        )
        try:
            return BuildingDataset(entities=entities)
        except ValueError as error:
            raise FixtureParseError(f"Malformed fixture: {error}") from error

    def _parse_entity(self, raw_entity: object, index: int) -> BuildingEntity:
        if not isinstance(raw_entity, dict):
            raise FixtureParseError(
                f"Malformed fixture entity at index {index}: expected an object."
            )

        required_fields = {
            "entity_id",
            "kind",
            "name",
            "global_id",
            "container_id",
            "attributes",
        }
        missing_fields = required_fields - raw_entity.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise FixtureParseError(
                f"Malformed fixture entity at index {index}: missing {missing}."
            )

        entity_id = raw_entity["entity_id"]
        kind = raw_entity["kind"]
        name = raw_entity["name"]
        global_id = raw_entity["global_id"]
        container_id = raw_entity["container_id"]
        attributes = raw_entity["attributes"]

        if not isinstance(entity_id, str) or not entity_id:
            raise FixtureParseError(
                f"Malformed fixture entity at index {index}: invalid entity_id."
            )
        if not isinstance(kind, str) or not kind:
            raise FixtureParseError(
                f"Malformed fixture entity at index {index}: invalid kind."
            )
        if name is not None and not isinstance(name, str):
            raise FixtureParseError(
                f"Malformed fixture entity at index {index}: invalid name."
            )
        if not isinstance(global_id, str) or not global_id:
            raise FixtureParseError(
                f"Malformed fixture entity at index {index}: invalid global_id."
            )
        if container_id is not None and not isinstance(container_id, str):
            raise FixtureParseError(
                f"Malformed fixture entity at index {index}: invalid container_id."
            )
        if not self._valid_attributes(attributes):
            raise FixtureParseError(
                f"Malformed fixture entity at index {index}: invalid attributes."
            )

        return BuildingEntity(
            entity_id=entity_id,
            kind=kind,
            name=name,
            global_id=global_id,
            container_id=container_id,
            attributes=attributes,
        )

    @staticmethod
    def _valid_attributes(attributes: object) -> bool:
        if not isinstance(attributes, dict):
            return False
        return all(
            isinstance(key, str)
            and (
                value is None
                or isinstance(value, (str, int, float, bool))
            )
            for key, value in attributes.items()
        )
