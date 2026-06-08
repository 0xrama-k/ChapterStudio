from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass

from backend.app.domain.models import ChapterGenerationError

log = logging.getLogger(__name__)


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
        self._usage = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self._usage_lock = threading.Lock()

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
        self._record_usage(payload.get("usage"))
        return LlmResponse(text=text)

    def usage_snapshot(self) -> dict[str, int]:
        with self._usage_lock:
            return dict(self._usage)

    def _record_usage(self, usage: object) -> None:
        provider_usage = usage if isinstance(usage, dict) else {}
        prompt_tokens = _usage_int(provider_usage, "prompt_tokens", "input_tokens")
        completion_tokens = _usage_int(provider_usage, "completion_tokens", "output_tokens")
        total_tokens = _usage_int(provider_usage, "total_tokens")
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens
        with self._usage_lock:
            self._usage["requests"] += 1
            self._usage["prompt_tokens"] += prompt_tokens
            self._usage["completion_tokens"] += completion_tokens
            self._usage["total_tokens"] += total_tokens
        log.info(
            "LLM usage model=%s prompt_tokens=%d completion_tokens=%d total_tokens=%d",
            self._model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )


def _usage_int(usage: dict, *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, int):
            return value
    return 0


class LlmContext:
    def __init__(self, llm: OpenAiCompatibleLlm) -> None:
        self.llm = llm
