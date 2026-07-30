"""
Provider architecture for LLM backends.
"""

from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):
    """Abstract base class for all LLM providers."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier for this provider instance."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the provider."""
        pass

    @abstractmethod
    def chat(self, model_id: str, messages: list[dict], tools: list[dict] | None = None, stream: bool = False) -> Any:
        """
        Send a chat completion request to the model.
        
        Args:
            model_id: The ID of the model to use.
            messages: List of message dictionaries (role, content).
            tools: List of tool definitions.
            stream: Whether to stream the response.
            
        Returns:
            A stream (generator) if stream=True, else a single response object.
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in the given text."""
        pass

    def get_capabilities(self) -> list[str]:
        """Return a list of capabilities this provider supports."""
        return ["chat"]
