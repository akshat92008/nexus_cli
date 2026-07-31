"""
Hosted provider implementation (OpenAI-compatible: NVIDIA, Groq, OpenRouter).
"""

import logging
import time
from typing import Any

# Temporarily alias NvidiaClient until it's fully migrated out of api.py
from nexus.api import NvidiaClient
from nexus.providers.base import Provider

logger = logging.getLogger(__name__)

_UNSET = object()  # Sentinel for optional parameters


class HostedProvider(Provider):
    """Adapter for hosted API providers (OpenAI-compatible).

    Wraps NvidiaClient and implements the full Provider protocol including
    chat_sync and proper forwarding of max_tokens / temperature kwargs.
    """

    def __init__(self, api_key: str | None = None, model_id: str | None = None):
        self._client = NvidiaClient(api_key=api_key)
        self._model_id = model_id  # The effective model string (e.g. 'z-ai/glm-5.2')

    # ── Provider protocol ────────────────────────────────────────────────────

    @property
    def id(self) -> str:
        return "hosted"

    @property
    def name(self) -> str:
        return "Hosted API Provider"

    @property
    def model_id(self) -> str:  # type: ignore[override]
        """Return the effective model string if one was set, otherwise fall back to id."""
        return self._model_id or self.id

    # ── Core chat methods ────────────────────────────────────────────────────

    def chat(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Streaming-capable chat with automatic rate-limit retry."""
        retries = 0
        max_retries = 3
        call_kwargs: dict[str, Any] = {}
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        call_kwargs.update(kwargs)

        while retries <= max_retries:
            try:
                return self._client.chat(
                    model_id=model_id,
                    messages=messages,
                    tools=tools,
                    stream=stream,
                    **call_kwargs,
                )
            except Exception as e:
                error_msg = str(e).lower()
                is_rate_limit = (
                    "429" in error_msg
                    or "rate" in error_msg
                    or "resourceexhausted" in error_msg
                    or "too many requests" in error_msg
                )
                if is_rate_limit and retries < max_retries:
                    retries += 1
                    wait_time = min(2 ** retries, 5)
                    logger.warning(
                        "Rate limited on %s, retrying in %ds...", self.name, wait_time
                    )
                    time.sleep(wait_time)
                else:
                    raise

    def chat_sync(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Non-streaming (blocking) chat completion."""
        call_kwargs: dict[str, Any] = {}
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        call_kwargs.update(kwargs)
        return self._client.chat_sync(
            model_id=model_id,
            messages=messages,
            tools=tools,
            **call_kwargs,
        )

    def count_tokens(self, text: str) -> int:
        if hasattr(self._client, "count_tokens"):
            return self._client.count_tokens(text)
        return len(text) // 4  # Fallback rough estimate
