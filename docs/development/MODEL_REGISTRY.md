# Model Registry & Backend Descriptors Specification

## Overview
The `ModelRegistry` in `nexus/models.py` provides a thread-safe, authoritative catalogue of all supported LLM backends in Nexus CLI.

## Model Attributes
Each `ModelDescriptor` contains:
- `model_id`: Provider specific model identifier.
- `provider_id`: Transport backend (`hosted`, `nova`, `custom`).
- `display_name`: Human readable title.
- `model_family`: Model architecture family (`llama`, `deepseek`, `glm`, `qwen`, `kimi`, `minimax`, `nemotron`, `nova`).
- `local`: Boolean flag indicating local compute.
- `tier`: `LOCAL`, `AFFORDABLE`, `STRONG`, `FRONTIER`.
- `privacy_class`: `LOCAL_ONLY`, `PRIVATE_INFRASTRUCTURE`, `APPROVED_CLOUD`, `ANY_ALLOWED_PROVIDER`.
- `input_cost`, `output_cost`, `cached_input_cost`: Pricing USD per 1,000,000 tokens.

## Supported Models
| Model Key | Display Name | Tier | Privacy Class | Context | Input Cost ($/1M) | Output Cost ($/1M) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `nova3b` | Nova Codex v11 | LOCAL | LOCAL_ONLY | 32,768 | 0.00 | 0.00 |
| `deepseek-flash` | DeepSeek V4 Flash | AFFORDABLE | APPROVED_CLOUD | 1,000,000 | 0.14 | 0.28 |
| `llama-3.3-70b` | Llama 3.3 70B | AFFORDABLE | APPROVED_CLOUD | 128,000 | 0.35 | 0.40 |
| `qwen3.5` | Qwen 3.5 397B | AFFORDABLE | APPROVED_CLOUD | 128,000 | 0.30 | 0.60 |
| `glm-5.2` | GLM 5.2 | STRONG | APPROVED_CLOUD | 1,000,000 | 0.50 | 1.00 |
| `deepseek-v4` | DeepSeek V4 Pro | STRONG | APPROVED_CLOUD | 1,000,000 | 0.55 | 2.19 |
| `kimi-k2.6` | Kimi K2.6 | STRONG | APPROVED_CLOUD | 262,144 | 0.60 | 2.50 |
| `minimax-m3` | MiniMax M3 | STRONG | APPROVED_CLOUD | 1,000,000 | 0.50 | 1.50 |
| `nemotron-super` | Nemotron Super 49B | STRONG | APPROVED_CLOUD | 128,000 | 0.60 | 1.20 |
| `custom` | Custom Hosted Model | FRONTIER | ANY_ALLOWED_PROVIDER | 200,000 | Configurable | Configurable |
