"""Multi-provider hosted inference client for the NexusAI runtime.

Supports multi-key NVIDIA rotation and a compatible Groq fallback.
"""

import os
import time
from pathlib import Path

from openai import OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Hosted inference can legitimately take more than a few seconds before the
# first token. Keep the defaults conservative while allowing operators to tune
# them for their environment.
DEFAULT_NVIDIA_TIMEOUT = float(os.environ.get("NEXUS_NVIDIA_TIMEOUT", "60.0"))
DEFAULT_GROQ_TIMEOUT = float(os.environ.get("NEXUS_GROQ_TIMEOUT", "60.0"))

# Groq model mappings for ultimate fallback (must support tool calling if used)
GROQ_MODEL_MAP = {
    "meta/llama-3.3-70b-instruct": "llama-3.3-70b-versatile",
    "deepseek-ai/deepseek-v4-pro": "openai/gpt-oss-120b",
    "deepseek-ai/deepseek-v4-flash": "openai/gpt-oss-120b",
    "z-ai/glm-5.2": "openai/gpt-oss-120b",
    "moonshotai/kimi-k2.6": "openai/gpt-oss-120b",
    "minimaxai/minimax-m3": "openai/gpt-oss-120b",
    "qwen/qwen3.5-397b-a17b": "openai/gpt-oss-120b",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": "openai/gpt-oss-120b",
    "meta/llama-3.1-70b-instruct": "openai/gpt-oss-120b",
}
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


def _load_env_file():
    """Load local Nexus environment files without overriding process values."""
    possible_paths = [
        os.path.expanduser("~/.config/nexus/.env"),
        os.path.expanduser("~/.nexusai/.env"),
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
                            # Explicit process environment wins over repository .env.
                            # This is required for CLI flags, CI, and isolated tests.
                            os.environ.setdefault(k, v)
            except Exception:
                pass


class RoundRobinKeyPool:
    """
    Thread-safe Round-Robin Pool Manager for API keys.
    Handles active key cycling, rate-limit cooldown tracking, and automatic key failover.
    """

    def __init__(self, keys: list[str], cooldown_seconds: float = 60.0):
        self.keys = list(dict.fromkeys([k for k in keys if k]))
        self.cooldown_seconds = cooldown_seconds
        self.current_idx = 0
        self.cooldowns: dict[str, float] = {}

    def get_next_key(self) -> str | None:
        """Select and return the next active round-robin key, skipping cooling-down keys."""
        if not self.keys:
            return None
        now = time.time()
        start_idx = self.current_idx
        for offset in range(len(self.keys)):
            idx = (start_idx + offset) % len(self.keys)
            key = self.keys[idx]
            if key not in self.cooldowns or now >= self.cooldowns[key]:
                self.current_idx = (idx + 1) % len(self.keys)
                return key
        earliest_key = min(self.keys, key=lambda k: self.cooldowns.get(k, 0))
        self.current_idx = (self.keys.index(earliest_key) + 1) % len(self.keys)
        return earliest_key

    def mark_cooldown(self, key: str, duration: float | None = None):
        """Mark a key as temporarily cooling down (e.g. on HTTP 429 rate limit)."""
        sec = duration if duration is not None else self.cooldown_seconds
        self.cooldowns[key] = time.time() + sec

    def is_cooldown(self, key: str) -> bool:
        """Check if a key is currently in cooldown."""
        return key in self.cooldowns and time.time() < self.cooldowns[key]

    def reset_cooldowns(self):
        """Reset all rate-limit cooldowns."""
        self.cooldowns.clear()


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
        self.key_cooldowns = {}

        # Round-Robin Key Pools
        self.nvidia_pool = RoundRobinKeyPool(self.nvidia_keys, cooldown_seconds=60.0)

        # Groq key fallback pool
        self.groq_keys = []
        if os.environ.get("GROQ_API_KEY"):
            self.groq_keys.append(os.environ["GROQ_API_KEY"])
        for k in sorted(os.environ.keys()):
            if (
                k.startswith("GROQ_API_KEY_")
                or k.startswith("GROQ_FALLBACK_API_KEY")
            ) and os.environ[k]:
                self.groq_keys.append(os.environ[k])
        self.groq_keys = list(dict.fromkeys([k for k in self.groq_keys if k]))
        self.groq_key = self.groq_keys[0] if self.groq_keys else ""
        self.groq_pool = RoundRobinKeyPool(self.groq_keys, cooldown_seconds=60.0)

        # Pre-instantiate primary client
        if self.nvidia_keys:
            self.client = OpenAI(
                base_url=NVIDIA_BASE_URL,
                api_key=self.nvidia_keys[0],
                timeout=self.timeout,
                max_retries=0,
            )
        elif self.groq_keys:
            self.client = OpenAI(
                base_url=GROQ_BASE_URL,
                api_key=self.groq_keys[0],
                timeout=DEFAULT_GROQ_TIMEOUT,
                max_retries=0,
            )
        elif os.environ.get("OPENROUTER_API_KEY"):
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"],
                timeout=DEFAULT_GROQ_TIMEOUT,
                max_retries=0,
            )
        else:
            raise ValueError("No valid API key found for NVIDIA, Groq, or OpenRouter.")

    @property
    def all_keys(self) -> list[str]:
        """Legacy compatibility property for existing codebase."""
        return self.nvidia_keys

    def get_next_key(self, provider: str = "nvidia") -> str | None:
        """Get the next active key via Round-Robin selection."""
        if provider.lower() == "groq":
            return self.groq_pool.get_next_key()
        key = self.nvidia_pool.get_next_key()
        if key and key in self.nvidia_keys:
            self.current_key_idx = self.nvidia_keys.index(key)
        return key

    def round_robin_rotate(self) -> str:
        """Explicit Round-Robin rotation to the next key in the pool."""
        next_key = self.get_next_key(provider="nvidia")
        if next_key:
            self.api_key = next_key
            self.client = self._get_nvidia_client(next_key)
        return self.api_key

    def switch_to_fallback(self) -> bool:
        """Switch round-robin to the next available NVIDIA key in the pool."""
        if len(self.nvidia_keys) > 1:
            self.round_robin_rotate()
            return True
        return False

    def _get_groq_client(self, key: str | None = None) -> OpenAI:
        """Get an OpenAI client configured for Groq API."""
        api_key = key or self.groq_key
        return OpenAI(
            base_url=GROQ_BASE_URL,
            api_key=api_key,
            timeout=DEFAULT_GROQ_TIMEOUT,
            max_retries=0,
        )

    def _get_nvidia_client(self, key: str) -> OpenAI:
        """Get an OpenAI client for a specific NVIDIA key."""
        return OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=key,
            timeout=self.timeout,
            max_retries=0,
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
        Tries NVIDIA keys, alternative NVIDIA models, Groq, then OpenRouter.
        """
        kwargs = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if stream:
            kwargs["stream_options"] = {"include_usage": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        errors = []
        connection_timed_out = False

        # ── Step 1: Try NVIDIA keys with requested model (max 3 key attempts for fast failover)
        if self.nvidia_keys:
            start_idx = self.current_key_idx
            now = time.time()
            max_attempts = min(3, len(self.nvidia_keys))
            attempted = 0
            for offset in range(len(self.nvidia_keys)):
                if attempted >= max_attempts:
                    break
                idx = (start_idx + offset) % len(self.nvidia_keys)
                key = self.nvidia_keys[idx]
                if key in self.key_cooldowns and now < self.key_cooldowns[key]:
                    continue  # Skip key currently in rate-limit cooldown
                attempted += 1
                try:
                    client = self._get_nvidia_client(key)
                    resp = client.chat.completions.create(model=model_id, **kwargs)
                    self.current_key_idx = (idx + 1) % len(self.nvidia_keys)
                    self.api_key = key
                    self.client = client
                    return resp
                except Exception as e:
                    err_str = str(e)
                    errors.append(f"NVIDIA Key {idx+1} ({model_id}): {err_str}")
                    if any(t in err_str.lower() for t in ("429", "rate limit", "too many requests")):
                        self.key_cooldowns[key] = time.time() + 60.0
                    if any(t in err_str.lower() for t in ("timeout", "timed out", "connection", "connect", "unreachable")):
                        connection_timed_out = True
                        break  # Fast exit on host timeout
                    self.switch_to_fallback()

        # ── Step 2: Try NVIDIA fallback models (DeepSeek Flash & Llama 3.3) ──
        if not connection_timed_out:
            fallback_nvidia_models = ["deepseek-ai/deepseek-v4-flash", "meta/llama-3.3-70b-instruct"]
            now = time.time()
            for fb_model in fallback_nvidia_models:
                if fb_model == model_id:
                    continue
                for idx, key in enumerate(self.nvidia_keys):
                    if key in self.key_cooldowns and now < self.key_cooldowns[key]:
                        continue
                    try:
                        client = self._get_nvidia_client(key)
                        resp = client.chat.completions.create(model=fb_model, **kwargs)
                        self.current_key_idx = (idx + 1) % len(self.nvidia_keys)
                        self.api_key = key
                        self.client = client
                        return resp
                    except Exception as e:
                        err_str = str(e)
                        errors.append(f"NVIDIA Fallback Model {fb_model} Key {idx+1}: {err_str}")
                        if any(t in err_str.lower() for t in ("429", "rate limit", "too many requests")):
                            self.key_cooldowns[key] = time.time() + 60.0
                        if any(t in err_str.lower() for t in ("timeout", "timed out", "connection", "connect", "unreachable")):
                            connection_timed_out = True
                            break
                if connection_timed_out:
                    break

        # ── Step 3: Ultimate Fallback to Groq API (multi-key & multi-model) ──
        if self.groq_keys:
            primary_groq = self.resolve_groq_model(model_id)
            groq_candidates = [
                primary_groq,
                "openai/gpt-oss-120b",
                "openai/gpt-oss-20b",
            ]
            groq_candidates = list(dict.fromkeys(groq_candidates))

            groq_kwargs = dict(kwargs)
            if groq_kwargs.get("max_tokens", 16384) > 32768:
                groq_kwargs["max_tokens"] = 32768

            for g_model in groq_candidates:
                for g_key in self.groq_keys:
                    try:
                        groq_client = self._get_groq_client(g_key)
                        return groq_client.chat.completions.create(model=g_model, **groq_kwargs)
                    except Exception as e:
                        err_str = str(e)
                        errors.append(f"Groq API Fallback ({g_model}): {err_str}")
                        if "429" in err_str or "rate limit" in err_str.lower() or "413" in err_str or "400" in err_str:
                            continue  # Try next model or key if rate-limited or invalid model

        # ── Step 4: Fallback to OpenRouter if a key is present ───────────────
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        if openrouter_key:
            try:
                or_client = OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=openrouter_key,
                    timeout=DEFAULT_GROQ_TIMEOUT,
                    max_retries=0,
                )
                or_kwargs = dict(kwargs)
                if or_kwargs.get("max_tokens", 16384) > 8192:
                    or_kwargs["max_tokens"] = 8192
                return or_client.chat.completions.create(model="deepseek/deepseek-chat", **or_kwargs)
            except Exception as e:
                errors.append(f"OpenRouter Fallback: {e}")

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
