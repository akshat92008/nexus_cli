"""
NVIDIA API client & Multi-Provider Resilient Client for NexusAI v2.0
Supports multi-key NVIDIA rotation and Groq API ultimate fallback.
"""

import os
import json
import time
from typing import Optional, List, Dict, Any, Tuple
from openai import OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Default timeouts for resilience
DEFAULT_NVIDIA_TIMEOUT = 15.0
DEFAULT_GROQ_TIMEOUT = 15.0

# Groq model mappings for ultimate fallback (must support tool calling if used)
GROQ_MODEL_MAP = {
    "meta/llama-3.3-70b-instruct": "llama-3.3-70b-versatile",
    "deepseek-ai/deepseek-v4-pro": "llama-3.3-70b-versatile",
    "deepseek-ai/deepseek-v4-flash": "llama-3.3-70b-versatile",
    "z-ai/glm-5.2": "llama-3.3-70b-versatile",
    "moonshotai/kimi-k2.6": "llama-3.3-70b-versatile",
    "minimaxai/minimax-m3": "llama-3.3-70b-versatile",
    "mistralai/codestral-22b-instruct-v0.1": "qwen-2.5-32b",
    "qwen/qwen3.5-397b-a17b": "qwen-2.5-32b",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": "llama-3.3-70b-versatile",
    "meta/llama-3.1-70b-instruct": "llama-3.1-70b-versatile",
}
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


def _load_env_file():
    """Load environment variables from .env files if present."""
    possible_paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.expanduser("~/Desktop/coding_agent/.env"),
        os.path.expanduser("~/Desktop/JARVIS/.env"),
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            os.environ[k] = v
            except Exception:
                pass


class NvidiaClient:
    """
    Multi-Provider & Multi-Key Resilient Client for NexusAI.
    Handles automatic round-robin key rotation across NVIDIA API keys,
    NVIDIA model fallbacks, and seamless Groq API ultimate failover.
    """

    def __init__(self, api_key: str | None = None, timeout: float = DEFAULT_NVIDIA_TIMEOUT):
        _load_env_file()
        self.primary_key = api_key or os.environ.get("NVIDIA_API_KEY", "")
        self.api_key = self.primary_key
        self.timeout = timeout

        # Collect all NVIDIA keys
        self.nvidia_keys = [self.primary_key] if self.primary_key else []
        for k in sorted(os.environ.keys()):
            if (
                k.startswith("NVIDIA_FALLBACK_API_KEY")
                or k.startswith("NVIDIA_API_KEY_")
            ) and os.environ[k]:
                self.nvidia_keys.append(os.environ[k])

        # Deduplicate keys while preserving insertion order
        self.nvidia_keys = list(dict.fromkeys([k for k in self.nvidia_keys if k]))
        self.current_key_idx = 0

        # Groq key fallback
        self.groq_key = os.environ.get(
            "GROQ_API_KEY",
            "",
        )

        # Pre-instantiate primary client
        if self.nvidia_keys:
            self.client = OpenAI(
                base_url=NVIDIA_BASE_URL,
                api_key=self.nvidia_keys[0],
                timeout=self.timeout,
            )
        elif self.groq_key:
            self.client = OpenAI(
                base_url=GROQ_BASE_URL,
                api_key=self.groq_key,
                timeout=DEFAULT_GROQ_TIMEOUT,
            )
        else:
            raise ValueError("No valid API key found for NVIDIA or Groq.")

    @property
    def all_keys(self) -> list[str]:
        """Legacy compatibility property for existing codebase."""
        return self.nvidia_keys

    def switch_to_fallback(self) -> bool:
        """Switch round-robin to the next available NVIDIA key in the pool."""
        if len(self.nvidia_keys) > 1:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.nvidia_keys)
            self.api_key = self.nvidia_keys[self.current_key_idx]
            self.client = OpenAI(
                base_url=NVIDIA_BASE_URL,
                api_key=self.api_key,
                timeout=self.timeout,
            )
            return True
        return False

    def _get_groq_client(self) -> OpenAI:
        """Get an OpenAI client configured for Groq API."""
        return OpenAI(
            base_url=GROQ_BASE_URL,
            api_key=self.groq_key,
            timeout=DEFAULT_GROQ_TIMEOUT,
        )

    def _get_nvidia_client(self, key: str) -> OpenAI:
        """Get an OpenAI client for a specific NVIDIA key."""
        return OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=key,
            timeout=self.timeout,
        )

    def resolve_groq_model(self, model_id: str) -> str:
        """Map an NVIDIA model ID to an equivalent Groq model ID."""
        return GROQ_MODEL_MAP.get(model_id, DEFAULT_GROQ_MODEL)

    def chat(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 16384,
        stream: bool = True,
    ):
        """
        Send a chat completion request with automatic multi-key and multi-provider failover.
        Tries NVIDIA Keys -> Alternative NVIDIA Models -> Groq API.
        """
        kwargs = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        errors = []

        # ── Step 1: Try NVIDIA keys with requested model ─────────────────────
        if self.nvidia_keys:
            start_idx = self.current_key_idx
            for offset in range(len(self.nvidia_keys)):
                idx = (start_idx + offset) % len(self.nvidia_keys)
                key = self.nvidia_keys[idx]
                try:
                    client = self._get_nvidia_client(key)
                    resp = client.chat.completions.create(model=model_id, **kwargs)
                    self.current_key_idx = idx
                    self.api_key = key
                    self.client = client
                    return resp
                except Exception as e:
                    err_str = str(e)
                    errors.append(f"NVIDIA Key {idx+1} ({model_id}): {err_str}")
                    self.switch_to_fallback()

        # ── Step 2: Try NVIDIA fallback models (DeepSeek Flash & Llama 3.3) ──
        fallback_nvidia_models = ["deepseek-ai/deepseek-v4-flash", "meta/llama-3.3-70b-instruct"]
        for fb_model in fallback_nvidia_models:
            if fb_model == model_id:
                continue
            for idx, key in enumerate(self.nvidia_keys):
                try:
                    client = self._get_nvidia_client(key)
                    resp = client.chat.completions.create(model=fb_model, **kwargs)
                    self.current_key_idx = idx
                    self.api_key = key
                    self.client = client
                    return resp
                except Exception as e:
                    errors.append(f"NVIDIA Fallback Model {fb_model} Key {idx+1}: {e}")

        # ── Step 3: Ultimate Fallback to Groq API ───────────────────────────
        if self.groq_key:
            groq_model = self.resolve_groq_model(model_id)
            try:
                groq_client = self._get_groq_client()
                groq_kwargs = dict(kwargs)
                if groq_kwargs.get("max_tokens", 16384) > 8192:
                    groq_kwargs["max_tokens"] = 8192

                return groq_client.chat.completions.create(model=groq_model, **groq_kwargs)
            except Exception as e:
                errors.append(f"Groq API Fallback ({groq_model}): {e}")

        # If all providers and keys failed, raise a clear exception with details
        summary_err = " | ".join(errors[-3:]) if errors else "All API attempts failed"
        raise RuntimeError(f"Nexus AI Provider Failover Error: {summary_err}")

    def chat_sync(
        self,
        model_id: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 16384,
    ):
        """Non-streaming chat completion with full multi-provider failover."""
        return self.chat(
            model_id=model_id,
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

