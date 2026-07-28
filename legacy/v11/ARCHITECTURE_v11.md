# Nova 3B System Architecture (Amaura)

Nova 3B is a production-grade, local-first AI coding engine developed by Amaura. This document outlines the core architectural components that power the multi-agent pipeline.

## Core Philosophy

1. **Speed over Size** — A 3B model at 38 t/s beats a 70B model at 2 t/s for execution.
2. **Format over Freedom** — Strict output protocols enable reliable automation.
3. **Execution over Reasoning** — Deep thinking is offloaded to the Ceiling node.
4. **Honesty over Hype** — Real benchmarks, acknowledged limitations, zero fabrication.

## Multi-Agent Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   User      │────▶│  Ceiling    │────▶│   Intern    │
│   Request   │     │  (Remote)   │     │  (Nova 3B)  │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
                           │                    │
                    Decomposes into       Executes each in
                    atomic tasks          strict format
                           │                    │
                           ▼                    ▼
                    ┌─────────────┐     ┌─────────────┐
                    │  Task List  │     │  Output     │
                    │  (JSON)     │     │  Parser     │
                    └─────────────┘     └──────┬──────┘
                                               │
                                        ┌──────▼──────┐
                                        │  Test       │
                                        │  Executor   │
                                        └─────────────┘
```

## System Components

### 1. Ceiling Node (`pipeline.py` → `CeilingNode`)
The reasoning brain — handles task decomposition via remote API.
- Receives complex requests from the user
- Decomposes into atomic, single-file tasks
- Provides context and ordering (dependency graph)
- Uses GPT-4o / Claude / DeepSeek / local Ollama

### 2. Intern Node (`pipeline.py` → `InternNode`)
The execution engine — generates code via local Ollama.
- Receives one atomic task at a time
- Generates code in strict `<<THINKING>>/<<FILES>>/<<TEST_COMMAND>>` format
- Runs at ~38 tokens/sec on 8GB M3 Mac
- Retries with stronger prompts on format failure

### 3. Output Parser (`output_parser.py`)
Strict regex parser for the Nova protocol.
- Extracts `<<THINKING>>`, `<<FILES>>`, `<<TEST_COMMAND>>` blocks
- Handles edge cases: missing tags, malformed fences, multi-block outputs
- Returns structured `ParsedResponse` with `FileAction` objects
- Validates format compliance (block order, thinking brevity)

### 4. Ollama Client (`ollama_client.py`)
Zero-dependency HTTP wrapper for Ollama's REST API.
- Generation (raw prompt + system prompt)
- Chat (multi-turn messages)
- Streaming with real-time token display
- Performance metrics (TPS, TTFT)
- Model management (list, create, check)

### 5. ReAct Agent (`agents.py`)
Autonomous reasoning loop with tool execution.
- Thought → Action → Observation cycle
- Integrates with ToolExecutor for sandboxed execution
- State management and conversation history

### 6. Dataset Generator (`generate_nova3b_dataset.py`)
Parametric, multi-backend dataset generation.
- **Free Colab path:** Qwen 7B teacher on T4 GPU
- **API path:** DeepSeek / OpenAI
- 7 task categories with configurable weights
- Validation, deduplication, and checkpoint/resume

### 7. Training Pipeline (`train_nova3b_colab.py`)
QLoRA fine-tuning on Google Colab.
- Qwen2.5-Coder-3B-Instruct base model
- System prompt injected into every training example
- 10% eval split for overfitting detection
- Automatic GGUF Q4_K_M export

### 8. Benchmark Harness (`benchmark_harness.py`)
Empirical evaluation against standard benchmarks.
- HumanEval, MBPP execution
- True pass@1 via sandboxed execution
- Compile rate and latency tracking

### 9. Self-Improvement Loop (`self_improve.py`)
Autonomous continuous learning.
- Generate → Execute → Analyze → Retrain cycle
- Identifies weak domains from failure analysis
- Generates targeted training data

### 10. Semantic Memory (`memory.py`)
Cross-session context persistence.
- Dense vector embeddings (SentenceTransformers)
- Prevents repeated mistakes
- Retrieves relevant past solutions

## Hardware Profile

| Resource | Budget |
|---|---|
| macOS + Services | ~2.0 GB |
| IDE + Browser | ~1.5 GB |
| **Nova 3B (Q4_K_M)** | **~2.2 GB** |
| KV Cache (4096 ctx) | ~0.5 GB |
| **Headroom** | ~1.8 GB |

---

**Amaura Engineering** — *Building verifiable intelligence.*
