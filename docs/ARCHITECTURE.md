# Nova v12 — System Architecture

## Core Philosophy

1. **Execution over Assertion** — Every training example is verified by compilation and testing
2. **Modes over Monolith** — Explicit control tokens route behaviour, not a single rigid template
3. **Local-First** — Models must run on consumer hardware without cloud dependencies
4. **Honest Evaluation** — Public benchmarks, raw outputs, failure cases, reproducible claims

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AMAURA NOVA CODE                             │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Nova Code   │  │  Nova Code   │  │  Nova Code   │              │
│  │    Lite      │  │     4B       │  │     8B       │              │
│  │  (autocmpl)  │  │   (hero)     │  │  (strong)    │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                 │                       │
│         └─────────────────┼─────────────────┘                       │
│                           │                                         │
│              ┌────────────▼────────────┐                            │
│              │   Shared Interface      │                            │
│              │   - Mode tokens         │                            │
│              │   - Tool-call format    │                            │
│              │   - Output protocols    │                            │
│              │   - FIM format          │                            │
│              └────────────┬────────────┘                            │
│                           │                                         │
│    ┌──────────┬───────────┼───────────┬──────────┬────────┐        │
│    ▼          ▼           ▼           ▼          ▼        ▼        │
│  Ollama    llama.cpp    MLX       Transformers  vLLM    LM Studio  │
│  GGUF      GGUF        MLX 4-bit  BF16/FP16    BF16    GGUF       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Training Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                    6-STAGE TRAINING RECIPE                    │
│                                                              │
│  Stage 1: Domain-Adaptive Continued Pretraining              │
│  ├── Next-token prediction on filtered code                  │
│  ├── Fill-in-the-middle objective                            │
│  ├── Diff prediction                                         │
│  └── Test-to-code / Code-to-test generation                  │
│                                                              │
│  Stage 2: Multi-Mode Supervised Fine-Tuning                  │
│  ├── Code generation (<|nova_code|>)                         │
│  ├── FIM completion (<|nova_fim|>)                           │
│  ├── Code editing (<|nova_edit|>)                            │
│  ├── Debugging (<|nova_debug|>)                              │
│  ├── Agentic tool use (<|nova_agent|>)                       │
│  └── Review / Explain / Refactor modes                       │
│                                                              │
│  Stage 3: Teacher Distillation                               │
│  ├── Multi-teacher ensemble generation                       │
│  ├── Sandbox execution verification                          │
│  └── Only verified outputs retained                          │
│                                                              │
│  Stage 4: Execution-Ranked Preference Optimisation (DPO)     │
│  ├── Same task → multiple candidates                         │
│  ├── Rank by execution results                               │
│  └── passes_all > passes_some > compiles > invalid           │
│                                                              │
│  Stage 5: Verifiable-Reward Reinforcement Learning           │
│  ├── GRPO / PPO with environment feedback                    │
│  ├── Rewards: patch applies, tests pass, minimal change      │
│  └── Penalties: hallucinated APIs, broken builds             │
│                                                              │
│  Stage 6: Quantisation-Aware Optimisation                    │
│  ├── BF16 → Q8 → Q6 → Q5 → Q4_K_M → Q3_K_M               │
│  ├── Evaluate each level on full benchmark suite             │
│  └── QAT if significant degradation detected                │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                     DATA FACTORY                             │
│                                                             │
│  Sources                    Processing          Outputs     │
│  ────────                   ──────────          ───────     │
│                                                             │
│  The Stack v2    ──┐                                        │
│  (streaming)       │        ┌──────────┐                    │
│                    ├──────▶ │ Licence  │                    │
│  Git histories   ──┤        │ Filter   │                    │
│  (diffs/commits)   │        └────┬─────┘                    │
│                    │             │                           │
│  Bug injection   ──┤        ┌────▼─────┐    ┌───────────┐  │
│  (mutations)       ├──────▶ │ Quality  │──▶│ Dedup     │  │
│                    │        │ Scorer   │    │ (3-level) │  │
│  Teacher models  ──┤        └────┬─────┘    └─────┬─────┘  │
│  (ensemble)        │             │                │         │
│                    │        ┌────▼─────┐    ┌─────▼─────┐  │
│  Nexus logs      ──┘        │ Contam.  │──▶│ Execution │  │
│  (with consent)             │ Check    │    │ Verifier  │  │
│                             └──────────┘    └─────┬─────┘  │
│                                                   │         │
│                             ┌──────────────────────┘         │
│                             ▼                               │
│                    ┌─────────────────┐                      │
│                    │ Training Data   │                      │
│                    │ ─────────────── │                      │
│                    │ • Code tokens   │                      │
│                    │ • FIM samples   │                      │
│                    │ • SFT examples  │                      │
│                    │ • DPO pairs     │                      │
│                    │ • Trajectories  │                      │
│                    │ • Repo seqs     │                      │
│                    └─────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Evaluation Architecture

```
┌──────────────────────────────────────────────────────┐
│                  EVALUATION SUITE                     │
│                                                      │
│  Code Generation        Repository & Editing         │
│  ───────────────        ────────────────────         │
│  • HumanEval+           • RepoBench                  │
│  • MBPP+                • CrossCodeEval              │
│  • LiveCodeBench        • SWE-bench Lite             │
│  • BigCodeBench                                      │
│                                                      │
│  Agentic & Tool Use     Completion                   │
│  ──────────────────     ──────────                   │
│  • Tool-call accuracy   • FIM exact match            │
│  • Multi-turn repair    • Compilation rate            │
│  • Terminal-Bench       • IDE latency                 │
│                                                      │
│  Local Performance      Private                      │
│  ─────────────────      ───────                      │
│  • Tokens/second        • Amaura CodeArena           │
│  • Time to first token  • Held-out tasks (500-1000)  │
│  • Peak memory          • Regression suite           │
│  • Quant comparison                                  │
└──────────────────────────────────────────────────────┘
```

---

## Deployment Targets

| Format    | Runtime                | Intended Use                    |
| --------- | ---------------------- | ------------------------------- |
| BF16      | Transformers / vLLM    | GPU inference and training      |
| Q8 GGUF   | llama.cpp / Ollama     | High-quality local use          |
| Q5_K_M    | llama.cpp / Ollama     | Balanced deployment             |
| Q4_K_M    | llama.cpp / Ollama     | Default consumer-laptop release |
| Q3_K_M    | llama.cpp / Ollama     | Constrained systems             |
| MLX 4-bit | MLX                    | Apple Silicon native            |
| AWQ/GPTQ  | vLLM / TGI             | GPU serving                     |

---

## Integration Points

Nova Code is designed to work in:
- **NexusAI** — Native intelligence layer
- **Ollama** — `ollama run amauralabs/nova-code`
- **Continue** — IDE coding assistant
- **Cline** — Autonomous coding agent
- **VS Code** — Extension and inline completion
- **JetBrains** — Plugin integration
- **Neovim** — LSP-style completion
- **LM Studio** — Desktop model runner
- **OpenAI-compatible APIs** — Drop-in replacement

---

*Amaura Labs — Building verifiable intelligence.*
