"""
Cost-aware routing and fallback for LLM providers.
"""

import logging
from typing import Any

from nexus.providers.base import Provider

logger = logging.getLogger(__name__)


class FallbackRouter(Provider):
    """Wraps multiple providers and handles automatic fallback if a provider fails.

    The router implements the full Provider protocol so that BudgetedClient and
    other wrappers can use it transparently — including chat_sync() and proper
    forwarding of max_tokens / temperature kwargs.
    """

    def __init__(self, primary: Provider, fallbacks: list[Provider] | None = None):
        self._primary = primary
        self._fallbacks = fallbacks or []
        self._active_provider = self._primary
        self._fallback_index = 0

    # ── Provider protocol ────────────────────────────────────────────────────

    @property
    def id(self) -> str:
        """Return the active provider's id rather than the hardcoded 'router' string.

        The engine uses ``provider.id`` as the model string fallback. Returning
        the active provider's id (e.g. 'hosted') means we don't accidentally
        send the literal string 'router' to the API.
        """
        return self._active_provider.id

    @property
    def model_id(self) -> str:  # type: ignore[override]
        """Delegate model_id to the currently active provider."""
        return self._active_provider.model_id

    @property
    def name(self) -> str:
        return f"Router (Active: {self._active_provider.name})"

    @property
    def attempt_telemetry_enabled(self) -> bool:
        providers = [self._primary, *self._fallbacks]
        return bool(providers) and all(
            getattr(provider, "attempt_telemetry_enabled", False) for provider in providers
        )

    # ── Fallback control ─────────────────────────────────────────────────────

    def switch_to_fallback(self) -> bool:
        """Switch to the next fallback provider. Returns True if successful."""
        if self._fallback_index < len(self._fallbacks):
            self._active_provider = self._fallbacks[self._fallback_index]
            self._fallback_index += 1
            logger.warning("Switched to fallback provider: %s", self._active_provider.name)
            return True
        return False

    def reset(self) -> None:
        """Reset back to the primary provider."""
        self._active_provider = self._primary
        self._fallback_index = 0

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
        try:
            return self._active_provider.chat(
                model_id,
                messages,
                tools,
                stream=stream,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
        except Exception as e:
            logger.warning("Provider %s failed: %s", self._active_provider.name, e)
            if self.switch_to_fallback():
                return self.chat(
                    model_id,
                    messages,
                    tools,
                    stream=stream,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )
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
        """Blocking (non-streaming) chat with automatic fallback."""
        try:
            return self._active_provider.chat_sync(
                model_id,
                messages,
                tools,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
        except Exception as e:
            logger.warning("Provider %s failed in chat_sync: %s", self._active_provider.name, e)
            if self.switch_to_fallback():
                return self.chat_sync(
                    model_id,
                    messages,
                    tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )
            raise

    def count_tokens(self, text: str) -> int:
        return self._active_provider.count_tokens(text)
