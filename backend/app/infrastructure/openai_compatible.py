from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from backend.app.domain.models import ChapterGenerationError


@dataclass(frozen=True)
class LlmResponse:
    text: str


class OpenAiCompatibleLlm:
    """Small adapter matching the `.complete(messages=...).text` plugin contract."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: int = 120) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> OpenAiCompatibleLlm:
        base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        api_key = os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL", "")
        if not api_key or not model:
            raise ChapterGenerationError("LLM_API_KEY and LLM_MODEL must be configured.")
        return cls(base_url=base_url, api_key=api_key, model=model)

    def complete(self, *, messages: list[dict[str, str]]) -> LlmResponse:
        body = json.dumps(
            {
                "model": self._model,
                "messages": messages,
                "max_tokens": 1200,
                "temperature": 0.2,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": "hermes-youtube-chapters/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            response_body = error.read().decode("utf-8", errors="replace").strip()
            detail = response_body[:1000] if response_body else error.reason
            raise ChapterGenerationError(
                f"LLM request failed with HTTP {error.code}: {detail}"
            ) from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ChapterGenerationError(f"LLM request failed: {error}") from error

        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ChapterGenerationError("LLM returned an unexpected response shape.") from error
        if not isinstance(text, str):
            raise ChapterGenerationError("LLM returned non-text content.")
        return LlmResponse(text=text)


class LlmContext:
    def __init__(self, llm: OpenAiCompatibleLlm) -> None:
        self.llm = llm
