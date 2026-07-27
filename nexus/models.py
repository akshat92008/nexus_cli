"""
Model registry — hosted NVIDIA models plus local Nova backends.
"""

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
        "context": 131072,
        "description": "MoE flagship — 128k context, top-tier reasoning & code",
        "supports_tools": True,
    },
    "deepseek-flash": {
        "id": "deepseek-ai/deepseek-v4-flash",
        "name": "DeepSeek V4 Flash",
        "category": "coding",
        "context": 131072,
        "description": "Ultra-fast DeepSeek MoE for rapid code generation & tool use",
        "supports_tools": True,
    },
    "glm-5.2": {
        "id": "z-ai/glm-5.2",
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
        "description": "Multimodal MoE by Moonshot AI — optimized for coding & tool use",
        "supports_tools": True,
    },
    "minimax-m3": {
        "id": "minimaxai/minimax-m3",
        "name": "MiniMax M3",
        "category": "general",
        "context": 131072,
        "description": "High-performance Mixture-of-Experts model by MiniMax",
        "supports_tools": True,
    },
    "codestral": {
        "id": "mistralai/codestral-22b-instruct-v0.1",
        "name": "Codestral 22B",
        "category": "coding",
        "context": 32768,
        "description": "Mistral AI's specialized model for code generation & editing",
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
    "code": "codestral",
    "codestral": "codestral",
    "nova": "nova3b",
    "nova-3b": "nova3b",
    "nova3b": "nova3b",
    "nova345": "nova3b",
    "nova3b11": "nova3b",
    "nova_codex": "nova3b",
    "local": "nova3b",
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
    """Resolve a model name or alias to its config dict."""
    key = resolve_model_key(name)
    return MODELS[key] if key else None


def list_models() -> list[dict]:
    """Return all models sorted by category."""
    results = []
    for key, cfg in sorted(MODELS.items(), key=lambda x: (x[1]["category"], x[0])):
        results.append({"key": key, **cfg})
    return results
