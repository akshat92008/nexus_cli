"""
Hosted provider implementation (OpenAI, Anthropic, NVIDIA, Groq).
"""

import logging
import time
from typing import Any

# Temporarily alias NvidiaClient until it's fully migrated out of api.py
from nexus.api import NvidiaClient
from nexus.providers.base import Provider

logger = logging.getLogger(__name__)

class HostedProvider(Provider):
    """Adapter for hosted API providers (OpenAI-compatible)."""

    def __init__(self, api_key: str | None = None):
        self._client = NvidiaClient(api_key=api_key)

    @property
    def id(self) -> str:
        return "hosted"

    @property
    def name(self) -> str:
        return "Hosted API Provider"

    def chat(self, model_id: str, messages: list[dict], tools: list[dict] | None = None, stream: bool = False) -> Any:
        retries = 0
        max_retries = 3
        while retries <= max_retries:
            try:
                return self._client.chat(model_id=model_id, messages=messages, tools=tools, stream=stream)
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
                    logger.warning("Rate limited on %s, retrying in %ds...", self.name, wait_time)
                    time.sleep(wait_time)
                else:
                    raise

    def count_tokens(self, text: str) -> int:
        if hasattr(self._client, "count_tokens"):
            return self._client.count_tokens(text)
        return len(text) // 4  # Fallback rough estimate
