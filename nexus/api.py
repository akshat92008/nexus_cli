"""
NVIDIA API client — OpenAI-compatible wrapper for integrate.api.nvidia.com
"""

import os
import json
from openai import OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaClient:
    """Thin wrapper around the OpenAI SDK pointed at NVIDIA's endpoint."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY", "")
        
        # Load all fallback keys from environment
        self.fallback_keys = []
        # Sort keys to ensure FALLBACK_API_KEY_1 comes before FALLBACK_API_KEY_2 etc.
        for k in sorted(os.environ.keys()):
            if k.startswith("NVIDIA_FALLBACK_API_KEY") and os.environ[k]:
                self.fallback_keys.append(os.environ[k])
                
        # Deduplicate and remove the primary key if it's in fallbacks
        self.fallback_keys = [k for k in dict.fromkeys(self.fallback_keys) if k != self.api_key]
        
        if not self.api_key:
            raise ValueError(
                "No NVIDIA API key found. Set NVIDIA_API_KEY env var or pass --api-key."
            )
        self.client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=self.api_key,
        )

    def switch_to_fallback(self) -> bool:
        """Switch to the next fallback API key if available."""
        if self.fallback_keys:
            self.api_key = self.fallback_keys.pop(0)
            self.client = OpenAI(
                base_url=NVIDIA_BASE_URL,
                api_key=self.api_key,
            )
            return True
        return False

    def chat(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 16384,
        stream: bool = True,
    ):
        """Send a chat completion request. Returns a stream or a response."""
        kwargs = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        return self.client.chat.completions.create(**kwargs)

    def chat_sync(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 16384,
    ):
        """Non-streaming chat completion."""
        return self.chat(
            model_id=model_id,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
