import json
import os
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class MissingLLMConfigurationError(RuntimeError):
    """Raised when required environment-based LLM configuration is missing."""


class LLMProviderError(RuntimeError):
    """Raised when the configured text provider cannot return a response."""


@dataclass(frozen=True, slots=True)
class LLMProviderSettings:
    api_key: str
    endpoint: str
    model: str

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "LLMProviderSettings":
        values = os.environ if environment is None else environment
        required = {
            "BIM_QA_LLM_API_KEY": values.get("BIM_QA_LLM_API_KEY"),
            "BIM_QA_LLM_ENDPOINT": values.get("BIM_QA_LLM_ENDPOINT"),
            "BIM_QA_LLM_MODEL": values.get("BIM_QA_LLM_MODEL"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise MissingLLMConfigurationError(
                "Missing LLM environment configuration: " + ", ".join(missing)
            )
        return cls(
            api_key=required["BIM_QA_LLM_API_KEY"],  # type: ignore[arg-type]
            endpoint=required["BIM_QA_LLM_ENDPOINT"],  # type: ignore[arg-type]
            model=required["BIM_QA_LLM_MODEL"],  # type: ignore[arg-type]
        )


class OpenAICompatibleChatProvider:
    """Thin configurable adapter for a chat-completions-compatible endpoint."""

    def __init__(self, settings: LLMProviderSettings, timeout: float = 30.0) -> None:
        self._settings = settings
        self._timeout = timeout

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        request_payload = json.dumps(
            {
                "model": self._settings.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        ).encode("utf-8")
        request = Request(
            self._settings.endpoint,
            data=request_payload,
            headers={
                "Authorization": f"Bearer {self._settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise LLMProviderError(
                    "LLM provider response content must be a string."
                )
            return content
        except (
            HTTPError,
            URLError,
            JSONDecodeError,
            IndexError,
            KeyError,
            TimeoutError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
        ) as error:
            raise LLMProviderError(f"LLM provider request failed: {error}") from error
