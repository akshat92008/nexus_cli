"""
Model registry — hosted NVIDIA models plus local Nova backends.
"""

import os

MODELS = {
    # ── Flagship Reasoning & Coding ──────────────────────────────────
    "llama-3.3-70b": {
        "id": "meta/llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B",
        "category": "coding",
        "context": 128000,
        "description": "Meta's flagship 70B — super fast, elite tool calling & agentic coding",
        "supports_tools": True,
    },
    "deepseek-v4": {
        "id": "deepseek-ai/deepseek-v4-pro",
        "name": "DeepSeek V4 Pro",
        "category": "reasoning",
        "context": 1_000_000,
        "description": "MoE flagship for long-context reasoning, coding, and agents",
        "supports_tools": True,
    },
    "deepseek-flash": {
        "id": "deepseek-ai/deepseek-v4-flash",
        "name": "DeepSeek V4 Flash",
        "category": "coding",
        "context": 1_000_000,
        "description": "Fast DeepSeek MoE for code generation and tool use",
        "supports_tools": True,
    },
    "glm-5.2": {
        "id": "z-ai/glm-5.2",
        "name": "GLM 5.2",
        "category": "reasoning",
        "context": 1_000_000,
        "description": "Flagship agentic, coding, and long-horizon reasoning model",
        "supports_tools": True,
    },
    "kimi-k2.6": {
        "id": "moonshotai/kimi-k2.6",
        "name": "Kimi K2.6",
        "category": "coding",
        "context": 262_144,
        "description": "Multimodal MoE optimized for long-horizon coding and tool use",
        "supports_tools": True,
    },
    "minimax-m3": {
        "id": "minimaxai/minimax-m3",
        "name": "MiniMax M3",
        "category": "general",
        "context": 1_000_000,
        "description": "Multimodal MoE for reasoning, coding, and tool calling",
        "supports_tools": True,
    },
    "qwen3.5": {
        "id": "qwen/qwen3.5-397b-a17b",
        "name": "Qwen 3.5 (397B)",
        "category": "coding",
        "context": 128000,
        "description": "Alibaba's 397B flagship MoE — specialized in software engineering",
        "supports_tools": True,
    },
    "nemotron-super": {
        "id": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "name": "Nemotron Super 49B",
        "category": "reasoning",
        "context": 128000,
        "description": "NVIDIA tuned Llama 3.3 for reasoning & complex tool execution",
        "supports_tools": True,
    },
    "llama-3.1-70b": {
        "id": "meta/llama-3.1-70b-instruct",
        "name": "Llama 3.1 70B",
        "category": "general",
        "context": 128000,
        "description": "Meta's highly capable 70B instruction-tuned model",
        "supports_tools": True,
    },
    "custom": {
        "id": "",
        "name": "Custom Hosted Model",
        "category": "custom",
        "context": 200000,
        "description": (
            "Any OpenAI-compatible or OpenRouter-hosted model. Pass --model-id "
            "or set NEXUS_MODEL_ID; a custom endpoint can be configured with "
            "NEXUS_OPENAI_BASE_URL and NEXUS_OPENAI_API_KEY."
        ),
        "supports_tools": True,
        "backend": "custom",
    },
    "nova3b": {
        "id": "local/nova3b",
        "name": "Nova Codex (Nova 3B v11)",
        "category": "local",
        "context": 32768,
        "description": (
            "Nova Codex (Nova 3B v11) — handles well-specified subtasks fast and free, locally. "
            "Guardrails validate paths, literal constraints, relevance, and disk-safe "
            "patching; failures are corrected once or escalated rather than silently applied."
        ),
        "supports_tools": True,
        "backend": "nova",
        "ollama_model": "nova_codex",
    },
}

# Aliases for convenience
ALIASES = {
    "llama": "llama-3.3-70b",
    "llama3": "llama-3.3-70b",
    "llama-3.3": "llama-3.3-70b",
    "deepseek": "deepseek-v4",
    "deepseek-v4": "deepseek-v4",
    "deepseek-v4-pro": "deepseek-v4",
    "deepseek-v4-flash": "deepseek-flash",
    "deepseek-pro": "deepseek-v4",
    "v4": "deepseek-v4",
    "v4-pro": "deepseek-v4",
    "ds": "deepseek-v4",
    "flash": "deepseek-flash",
    "glm": "glm-5.2",
    "glm-5.2": "glm-5.2",
    "kimi": "kimi-k2.6",
    "minimax": "minimax-m3",
    "qwen": "qwen3.5",
    "qwen-coder": "qwen3.5",
    "nemotron": "nemotron-super",
    "code": "qwen3.5",
    "nova": "nova3b",
    "nova-3b": "nova3b",
    "nova3b": "nova3b",
    "nova345": "nova3b",
    "nova3b11": "nova3b",
    "nova_codex": "nova3b",
    "local": "nova3b",
    "custom": "custom",
    "frontier": "custom",
    "openrouter": "custom",
}

DEFAULT_MODEL = "glm-5.2"


def resolve_model_key(name: str) -> str | None:
    """Resolve a model name or alias to its canonical registry key."""
    if not name:
        return DEFAULT_MODEL
    key = ALIASES.get(name.lower().strip(), name.lower().strip())
    if key in MODELS:
        return key
    for k, cfg in MODELS.items():
        if name.lower() in k or name.lower() in cfg["name"].lower():
            return k
    return None


def resolve_model(name: str) -> dict | None:
    """Resolve a model name or alias to an isolated config dictionary."""
    key = resolve_model_key(name)
    if not key:
        return None
    config = dict(MODELS[key])
    if key == "custom":
        config["id"] = os.environ.get("NEXUS_MODEL_ID", "").strip()
        if config["id"]:
            config["name"] = f"Custom Hosted Model ({config['id']})"
    return config


def list_models() -> list[dict]:
    """Return all models sorted by category."""
    results = []
    for key, cfg in sorted(MODELS.items(), key=lambda x: (x[1]["category"], x[0])):
        resolved = resolve_model(key) or dict(cfg)
        results.append({"key": key, **resolved})
    return results
