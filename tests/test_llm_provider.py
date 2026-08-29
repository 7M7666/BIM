import json

from bim_evidence_qa.query import (
    LLMProviderSettings,
    OpenAICompatibleChatProvider,
)
from bim_evidence_qa.query import llm_provider


class FakeHTTPResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"operation":"count","kind":"space"}'
                        }
                    }
                ]
            }
        ).encode("utf-8")


def test_provider_sends_deepseek_json_output_and_disables_thinking(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeHTTPResponse()

    monkeypatch.setattr(llm_provider, "urlopen", fake_urlopen)
    provider = OpenAICompatibleChatProvider(
        LLMProviderSettings(
            api_key="fake-test-key",
            endpoint="https://api.deepseek.com/chat/completions",
            model="deepseek-v4-flash",
        ),
        timeout=12.0,
    )

    response = provider.complete("Return JSON only.", '{"question":"count"}')

    assert response == '{"operation":"count","kind":"space"}'
    assert captured["payload"]["model"] == "deepseek-v4-flash"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["timeout"] == 12.0
