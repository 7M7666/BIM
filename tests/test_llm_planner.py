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
