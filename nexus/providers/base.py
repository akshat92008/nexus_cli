"""
Provider architecture for LLM backends.

All providers MUST implement this protocol exactly. Every wrapper in the chain
(HostedProvider, FallbackRouter, NovaProvider, BudgetedClient, test doubles)
must preserve both the synchronous and streaming forms and forward kwargs.
"""

from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):
    """Abstract base class for all LLM providers."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier for this provider instance (e.g. 'hosted', 'nova', 'router')."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the provider."""

    @property
    def model_id(self) -> str:
        """The effective model string to send to the API.

        Providers backed by a real model should override this to return the
        actual model identifier (e.g. 'z-ai/glm-5.2'). Defaults to ``id`` for
        backward-compatibility with providers that do not distinguish between
        the two concepts.
        """
        return self.id

    @abstractmethod
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
        """Send a chat completion request to the model.

        Args:
            model_id: The ID of the model to use.
            messages: List of message dictionaries (role, content).
            tools: List of tool definitions.
            stream: Whether to stream the response.
            max_tokens: Optional hard cap on completion tokens.
            temperature: Optional sampling temperature.
            **kwargs: Additional provider-specific parameters.

        Returns:
            A stream (generator / Iterator) if stream=True, else a single
            response object.
        """

    @abstractmethod
    def chat_sync(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Blocking (non-streaming) chat completion.

        Must be implemented by every provider. The two-node backend and any
        other synchronous code path rely exclusively on this method.
        """

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in the given text."""

    def get_capabilities(self) -> list[str]:
        """Return a list of capabilities this provider supports."""
        return ["chat", "chat_sync"]
