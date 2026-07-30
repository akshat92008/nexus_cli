"""
Cost-aware routing and fallback for LLM providers.
"""

import logging
from typing import Any

from nexus.providers.base import Provider

logger = logging.getLogger(__name__)


class FallbackRouter(Provider):
    """
    Wraps multiple providers and handles automatic fallback if a provider fails.
    """

    def __init__(self, primary: Provider, fallbacks: list[Provider] | None = None):
        self._primary = primary
        self._fallbacks = fallbacks or []
        
        self._active_provider = self._primary
        self._fallback_index = 0

    @property
    def id(self) -> str:
        return "router"

    @property
    def name(self) -> str:
        return f"Router (Active: {self._active_provider.name})"

    def switch_to_fallback(self) -> bool:
        """Switch to the next fallback provider. Returns True if successful."""
        if self._fallback_index < len(self._fallbacks):
            self._active_provider = self._fallbacks[self._fallback_index]
            self._fallback_index += 1
            logger.warning("Switched to fallback provider: %s", self._active_provider.name)
            return True
        return False

    def reset(self):
        """Reset back to the primary provider."""
        self._active_provider = self._primary
        self._fallback_index = 0

    def chat(self, model_id: str, messages: list[dict], tools: list[dict] | None = None, stream: bool = False) -> Any:
        try:
            return self._active_provider.chat(model_id, messages, tools, stream)
        except Exception as e:
            logger.warning("Provider %s failed: %s", self._active_provider.name, e)
            if self.switch_to_fallback():
                return self.chat(model_id, messages, tools, stream)
            raise

    def count_tokens(self, text: str) -> int:
        return self._active_provider.count_tokens(text)
