# Nova 3B — Local AI Coding Engine by Amaura

> *"Local intelligence. Zero compromise."*

**Nova 3B** is a hyper-specialized, 3-billion parameter coding execution engine designed to run at **~38 tokens/second** on an 8GB Apple M3 Mac. It serves as the "Intern" node in Amaura's multi-agent pipeline — receiving atomic coding tasks and executing them with surgical precision.

---

## ⚡ Performance

| Metric | Value |
|---|---|
| **Generation Speed** | ~38 tokens/sec |
| **Time to First Token** | ~3.4 seconds |
| **RAM Usage** | ~2.2 GB (Q4_K_M) |
| **Context Window** | 4,096 tokens |
| **Format Compliance** | >95% (post fine-tune) |

---

## 🏗️ Architecture

Nova operates as part of a **two-node multi-agent pipeline**:

```
┌──────────────────────────┐
│   USER REQUEST           │
│   "Build a REST API..."  │
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│   🧠 CEILING NODE        │
│   Remote API (GPT-4o /   │
│   Claude / DeepSeek)     │
│                          │
│   Decomposes into        │
│   atomic tasks           │
└───────────┬──────────────┘
            │ Task 1, Task 2, Task 3...
            ▼
┌──────────────────────────┐
│   ⚡ INTERN NODE          │
│   Nova 3B (Local Ollama) │
│                          │
│   Executes each task     │
│   in strict format       │
│   at 38 tokens/sec       │
└───────────┬──────────────┘
            │
            ▼
┌──────────────────────────┐
│   📋 OUTPUT PARSER        │
│   Extracts files, tests  │
│   Validates format       │
└──────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Deploy with Ollama

```bash
# One-command deploy
chmod +x deploy.sh
./deploy.sh

# Or manually
ollama create nova3b -f Modelfile.amaura
```

### 2. Run the Pipeline

```bash
# Direct generation
ollama run nova3b "Write a Python function to check if a number is prime"

# Multi-agent pipeline
python pipeline.py "Add a /health endpoint to the Flask API" --ceiling manual

# Smoke test
python smoke_test.py --model nova3b
```

### 3. Fine-Tune on Colab (Optional)

```bash
# Generate training data
python generate_nova3b_dataset.py --mode dry-run --count 100 --merge

# Upload to Colab, then run:
# !python train_nova3b_colab.py --dataset dataset_nova3b_combined.jsonl
```

---

## 📁 Project Structure

```
nova-1.5b/
├── 🎨 Brand & Docs
│   ├── BRAND_SPEC.md              # Amaura brand specification
│   ├── ARCHITECTURE.md            # System architecture
│   └── README.md                  # This file
│
├── 📊 Dataset Engineering
│   ├── dataset_categories.py      # Task category definitions
│   ├── generate_nova3b_dataset.py # Unified dataset generator
│   ├── validate_dataset.py        # Quality control
│   └── dataset_nova_intern_v5.jsonl # 964 verified examples
│
├── 🔧 Training
│   ├── train_nova3b_colab.py      # Production Colab training script
│   ├── Modelfile.amaura           # Production Ollama model config
│   └── train_unsloth.py           # Legacy training script
│
├── 🚀 Runtime & Pipeline
│   ├── pipeline.py                # Ceiling ↔ Intern orchestrator
│   ├── output_parser.py           # Strict format parser
│   ├── ollama_client.py           # Ollama HTTP client
│   └── agents.py                  # ReAct agent architecture
│
├── 🧪 Testing & Evaluation
│   ├── smoke_test.py              # Format compliance tests
│   ├── benchmark_harness.py       # HumanEval/MBPP harness
│   └── deploy.sh                  # One-command deployment
│
└── 🧠 Advanced
    ├── self_improve.py            # Autonomous improvement loop
    ├── retrieval.py               # RAG & AST indexing
    └── memory.py                  # Long-term semantic memory
```

---

## 🔧 Training Spec

| Parameter | Value |
|---|---|
| Base Model | `Qwen/Qwen2.5-Coder-3B-Instruct` |
| Method | QLoRA (4-bit NF4) via Unsloth |
| LoRA Rank | 32 |
| LoRA Alpha | 64 |
| Target Modules | All linear layers (q/k/v/o/gate/up/down) |
| Epochs | 3 |
| Learning Rate | 2e-4 (linear decay) |
| Batch Size | 2 × 4 gradient accumulation |
| Max Seq Length | 2048 |
| GGUF Quantization | Q4_K_M |

---

## 📋 Output Protocol

Nova responds in a strict, parseable format:

```
<<THINKING>>
I will create src/utils.py with a fibonacci function using iteration.

<<FILES>>
```python
# filepath: src/utils.py
# action: CREATE

def fibonacci(n: int) -> int:
    """Return the nth Fibonacci number."""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
```

<<TEST_COMMAND>>
pytest test_utils.py
```

---

## ⚠️ Known Limitations

1. **Hallucinations** — Will confidently invent APIs if context is incomplete
2. **Context Degradation** — Loses accuracy on 5+ file refactors
3. **No Architecture** — Cannot design systems; needs atomic task decomposition
4. **Python-Primary** — Best at Python; other languages may have format issues

---

## 📜 License

MIT — Built by **Amaura Engineering**

*Building verifiable intelligence.*
