"""
Model registry — all top-tier models available on NVIDIA's free API catalog.
"""

MODELS = {
    # ── Flagship Reasoning & Coding ──────────────────────────────────
    "deepseek-v4": {
        "id": "deepseek-ai/deepseek-v4-pro",
        "name": "DeepSeek V4 Pro",
        "category": "reasoning",
        "context": 131072,
        "description": "MoE flagship — 1M context, top-tier reasoning & code",
        "supports_tools": True,
    },
    "deepseek-r1": {
        "id": "deepseek-ai/deepseek-r1",
        "name": "DeepSeek R1",
        "category": "reasoning",
        "context": 131072,
        "description": "Deep reasoning model with chain-of-thought",
        "supports_tools": False,
    },
    "glm-5.2": {
        "id": "thudm/glm-5.2",
        "name": "GLM 5.2",
        "category": "reasoning",
        "context": 131072,
        "description": "Flagship agentic & reasoning LLM by Zhipu AI",
        "supports_tools": True,
    },
    "kimi-k2.6": {
        "id": "moonshotai/kimi-k2.6",
        "name": "Kimi K2.6",
        "category": "coding",
        "context": 131072,
        "description": "Multimodal MoE — optimized for coding & tool use",
        "supports_tools": True,
    },

    # ── NVIDIA Nemotron Family ───────────────────────────────────────
    "nemotron-ultra": {
        "id": "nvidia/nemotron-3-ultra-550b-a55b",
        "name": "Nemotron Ultra 550B",
        "category": "reasoning",
        "context": 131072,
        "description": "NVIDIA flagship — agentic reasoning, 550B params",
        "supports_tools": True,
    },
    "nemotron-super": {
        "id": "nvidia/llama-3.1-nemotron-70b-instruct",
        "name": "Nemotron 70B",
        "category": "general",
        "context": 131072,
        "description": "Fine-tuned Llama 3.1 70B by NVIDIA",
        "supports_tools": True,
    },

    # ── Qwen Family ─────────────────────────────────────────────────
    "qwen-2.5-72b": {
        "id": "qwen/qwen2.5-72b-instruct",
        "name": "Qwen 2.5 72B",
        "category": "general",
        "context": 131072,
        "description": "Alibaba's 72B flagship — strong code & math",
        "supports_tools": True,
    },
    "qwen-coder": {
        "id": "qwen/qwen2.5-coder-32b-instruct",
        "name": "Qwen 2.5 Coder 32B",
        "category": "coding",
        "context": 65536,
        "description": "Specialized coding model by Alibaba",
        "supports_tools": True,
    },

    # ── Meta Llama Family ────────────────────────────────────────────
    "llama-3.1-405b": {
        "id": "meta/llama-3.1-405b-instruct",
        "name": "Llama 3.1 405B",
        "category": "general",
        "context": 131072,
        "description": "Meta's largest open model — 405B params",
        "supports_tools": True,
    },
    "llama-3.1-70b": {
        "id": "meta/llama-3.1-70b-instruct",
        "name": "Llama 3.1 70B",
        "category": "general",
        "context": 131072,
        "description": "Strong all-rounder at 70B",
        "supports_tools": True,
    },

    # ── Mistral Family ──────────────────────────────────────────────
    "mixtral-8x22b": {
        "id": "mistralai/mixtral-8x22b-instruct-v0.1",
        "name": "Mixtral 8x22B",
        "category": "general",
        "context": 65536,
        "description": "Mistral MoE — fast and capable",
        "supports_tools": True,
    },
    "mistral-large": {
        "id": "mistralai/mistral-large-2-instruct",
        "name": "Mistral Large 2",
        "category": "reasoning",
        "context": 131072,
        "description": "Mistral's flagship large model",
        "supports_tools": True,
    },

    # ── Google Gemma ─────────────────────────────────────────────────
    "gemma-2-27b": {
        "id": "google/gemma-2-27b-it",
        "name": "Gemma 2 27B",
        "category": "general",
        "context": 8192,
        "description": "Google's efficient open model",
        "supports_tools": False,
    },
}

# Aliases for convenience
ALIASES = {
    "deepseek": "deepseek-v4",
    "ds": "deepseek-v4",
    "ds-r1": "deepseek-r1",
    "glm": "glm-5.2",
    "kimi": "kimi-k2.6",
    "nemotron": "nemotron-ultra",
    "qwen": "qwen-2.5-72b",
    "llama": "llama-3.1-405b",
    "mixtral": "mixtral-8x22b",
    "mistral": "mistral-large",
    "gemma": "gemma-2-27b",
}

DEFAULT_MODEL = "deepseek-v4"


def resolve_model(name: str) -> dict | None:
    """Resolve a model name or alias to its config dict."""
    key = ALIASES.get(name.lower(), name.lower())
    return MODELS.get(key)


def list_models() -> list[dict]:
    """Return all models sorted by category."""
    results = []
    for key, cfg in sorted(MODELS.items(), key=lambda x: (x[1]["category"], x[0])):
        results.append({"key": key, **cfg})
    return results
