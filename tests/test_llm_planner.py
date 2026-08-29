import json

import pytest

from bim_evidence_qa.application import run_question
from bim_evidence_qa.domain import AggregateFunction, QueryOperation
from bim_evidence_qa.query import (
    InvalidPlannerOutputError,
    LLMProviderSettings,
    LLMQueryPlanner,
    MissingLLMConfigurationError,
    QueryCatalog,
    UnsupportedQueryError,
)


class FakeProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.system_prompt = ""
        self.user_prompt = ""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.response


@pytest.fixture
def catalog(synthetic_dataset):
    return QueryCatalog.from_dataset(synthetic_dataset)


def test_llm_planner_returns_catalog_validated_plan(catalog):
    provider = FakeProvider(
        json.dumps(
            {
                "operation": "aggregate",
                "kind": "space",
                "aggregate_function": "max",
                "aggregate_field": "area",
            }
        )
    )

    plan = LLMQueryPlanner(provider).plan(
        "Which room has the largest area?", catalog
    )

    assert plan.operation is QueryOperation.AGGREGATE
    assert plan.kind == "space"
    assert plan.aggregate_function is AggregateFunction.MAX
    assert plan.aggregate_field == "area"
    assert "Do not answer the question" in provider.system_prompt
    assert '"attributes_by_kind"' in provider.user_prompt
    assert '"aggregate_functions"' in provider.user_prompt
    assert '"valid_query_plan_examples"' in provider.user_prompt
    assert '"unsupported_example"' in provider.user_prompt
    assert "English or Chinese" in provider.system_prompt
    assert "Never substitute the nearest available concept" in provider.system_prompt
    assert "absent elevator is not a door" in provider.system_prompt
    assert "absent stairs are not a storey" in provider.system_prompt
    assert "absent column is not a wall" in provider.system_prompt


def test_validated_llm_plan_enters_grounded_application_flow(synthetic_dataset):
    provider = FakeProvider(
        json.dumps(
            {
                "operation": "aggregate",
                "kind": "space",
                "aggregate_function": "max",
                "aggregate_field": "area",
            }
        )
    )

    outcome = run_question(
        synthetic_dataset,
        "Which room has the largest area?",
        LLMQueryPlanner(provider),
    )

    assert outcome.result.value == outcome.answer.value == 30.0
    assert outcome.answer.evidence[0].name == "Room 202"
    assert (
        outcome.answer.evidence[0].global_id
        == outcome.result.entities[0].global_id
        == "SYNTHETIC-SPACE-202"
    )


def test_llm_planner_rejects_invalid_kind(catalog):
    provider = FakeProvider(
        json.dumps({"operation": "count", "kind": "elevator"})
    )

    with pytest.raises(
        InvalidPlannerOutputError,
        match="unavailable entity kind 'elevator'",
    ):
        LLMQueryPlanner(provider).plan("How many elevators?", catalog)


def test_llm_planner_rejects_invalid_attribute_for_kind(catalog):
    provider = FakeProvider(
        json.dumps(
            {
                "operation": "aggregate",
                "kind": "door",
                "aggregate_function": "average",
                "aggregate_field": "area",
            }
        )
    )

    with pytest.raises(
        InvalidPlannerOutputError,
        match="Attribute 'area' is unavailable for entity kind 'door'",
    ):
        LLMQueryPlanner(provider).plan("Average door area", catalog)


def test_llm_planner_rejects_malformed_json(catalog):
    provider = FakeProvider("not valid json")

    with pytest.raises(
        InvalidPlannerOutputError,
        match="malformed JSON",
    ):
        LLMQueryPlanner(provider).plan("How many rooms?", catalog)


def test_llm_planner_rejects_unsupported_operation(catalog):
    provider = FakeProvider(
        json.dumps({"operation": "relationship", "kind": "space"})
    )

    with pytest.raises(
        InvalidPlannerOutputError,
        match="unsupported operation 'relationship'",
    ):
        LLMQueryPlanner(provider).plan("Which rooms connect?", catalog)


def test_llm_planner_accepts_explicit_unsupported_response(catalog):
    provider = FakeProvider(
        json.dumps({"unsupported": "color is unavailable in the catalog"})
    )

    with pytest.raises(UnsupportedQueryError, match="LLM planner rejected question"):
        LLMQueryPlanner(provider).plan("What color is Room 101?", catalog)


def test_query_catalog_prompt_changes_with_dataset_content(
    synthetic_dataset,
    development_ifc_dataset,
):
    synthetic_payload = QueryCatalog.from_dataset(
        synthetic_dataset
    ).as_prompt_payload()
    ifc_payload = QueryCatalog.from_dataset(
        development_ifc_dataset
    ).as_prompt_payload()

    assert synthetic_payload["kinds"] == ["door", "space", "storey"]
    assert ifc_payload["kinds"] == [
        "door",
        "space",
        "storey",
        "wall",
        "window",
    ]
    assert "Room 202" in synthetic_payload["entity_names"]
    assert "Room 202" not in ifc_payload["entity_names"]
    assert ifc_payload["aggregate_functions"] == ["average", "max", "min"]


def test_llm_settings_require_environment_configuration():
    with pytest.raises(
        MissingLLMConfigurationError,
        match="BIM_QA_LLM_API_KEY",
    ):
        LLMProviderSettings.from_environment({})


def test_llm_settings_read_key_endpoint_and_model_from_environment():
    settings = LLMProviderSettings.from_environment(
        {
            "BIM_QA_LLM_API_KEY": "test-key",
            "BIM_QA_LLM_ENDPOINT": "https://example.invalid/chat/completions",
            "BIM_QA_LLM_MODEL": "test-model",
        }
    )

    assert settings.api_key == "test-key"
    assert settings.endpoint.endswith("/chat/completions")
    assert settings.model == "test-model"
