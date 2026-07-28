# Nova v12 — Training Recipe

## Overview

Nova Code 4B is trained through a 6-stage pipeline. Each stage has an entry gate
(the previous stage must pass its evaluation) and an exit gate (the model must
improve or at minimum not degrade on key metrics).

---

## Stage 1: Domain-Adaptive Continued Pretraining (CPT)

**Goal:** Strengthen the foundation's code knowledge without catastrophic forgetting.

### Data
- High-quality source code (filtered, deduplicated, licensed)
- Documentation, diffs, commit messages, build files
- Repository-level sequences (cross-file context)

### Objectives
- Next-token prediction (primary)
- Fill-in-the-middle (FIM)
- Diff prediction
- Test-to-code and code-to-test generation

### Hyperparameters (Starting Point)
| Parameter | Value |
|---|---|
| Learning rate | 1e-5 to 5e-5 (cosine decay) |
| Warmup | 2-5% of total steps |
| Batch size | As large as memory allows |
| Max sequence length | 4096–8192 tokens |
| Gradient accumulation | Adjusted for effective batch |
| Weight decay | 0.01–0.1 |
| BF16 / FP16 | BF16 preferred |

### Monitoring
- Training loss and perplexity
- FIM accuracy on held-out set
- HumanEval pass@1 (should not drop)
- MBPP pass@1 (should not drop)

### Exit Gate
- Perplexity improves on code-specific validation set
- No more than 2% degradation on general reasoning benchmarks
- FIM accuracy measurably improves

---

## Stage 2: Multi-Mode Supervised Fine-Tuning (SFT)

**Goal:** Teach all Nova operating modes using verified examples.

### Data Mix
| Mode | Allocation | Token |
|---|---:|---|
| Code generation | 30% | `<\|nova_code\|>` |
| FIM completion | 20% | `<\|nova_fim\|>` |
| Code editing | 15% | `<\|nova_edit\|>` |
| Debugging | 15% | `<\|nova_debug\|>` |
| Agentic tool use | 10% | `<\|nova_agent\|>` |
| Review/Explain/Refactor | 10% | Various |

### Method
- Full fine-tuning if compute allows, otherwise QLoRA
- QLoRA config: rank=64, alpha=128, target all linear layers
- Use Unsloth or TRL

### Hyperparameters
| Parameter | Value |
|---|---|
| Learning rate | 1e-5 to 2e-5 |
| Epochs | 2–3 |
| Batch size | 2–4 with gradient accumulation |
| Max sequence length | 4096–8192 |
| Eval split | 10% |

### Exit Gate
- HumanEval+ improves over Stage 1 output
- FIM accuracy maintained or improved
- Tool-call format correctness ≥ 95%
- Mode tokens produce distinct, appropriate behaviours

---

## Stage 3: Teacher Distillation

**Goal:** Transfer high-quality reasoning patterns from stronger models.

### Process
1. Select tasks that Nova currently fails or handles poorly
2. Generate candidates from teacher ensemble (DeepSeek-V3, Qwen-72B, etc.)
3. Execute all candidates in sandbox
4. Retain only verified passing solutions
5. Format as SFT examples with the appropriate mode token
6. Fine-tune Nova on the verified teacher outputs

### Teachers (Open-Weight Priority)
- DeepSeek-V3 (or Coder variant)
- Qwen2.5-72B-Instruct
- Qwen3-Coder (for tool-use patterns)
- Any strong open model available at training time

### Exit Gate
- Improvement on tasks where Nova previously failed
- No regression on tasks Nova already handled well
- Teacher-distilled examples are genuinely execution-verified

---

## Stage 4: Execution-Ranked Preference Optimisation (DPO/ORPO)

**Goal:** Teach the model to prefer correct, minimal solutions over plausible but broken ones.

### Data
For each task, generate multiple candidates and rank by execution:
```
passes_all_tests + minimal_change  → rank 1 (chosen)
passes_all_tests + excessive_change → rank 2
compiles_but_fails_tests           → rank 3
does_not_compile                   → rank 4 (rejected)
```

### Method
- DPO (Direct Preference Optimisation) or ORPO
- β = 0.1 (starting point, tune on validation)
- Use TRL's DPOTrainer

### Hyperparameters
| Parameter | Value |
|---|---|
| Learning rate | 5e-7 to 5e-6 |
| β (DPO) | 0.1 |
| Epochs | 1–2 |
| Max sequence length | 4096–8192 |

### Exit Gate
- Model prefers compilation-passing solutions more often
- Test-pass rate improves on held-out tasks
- No regression on HumanEval+/MBPP+

---

## Stage 5: Verifiable-Reward Reinforcement Learning

**Goal:** Online optimisation against real execution environments.

### Reward Signals (Positive)
```
+1.0  Hidden tests pass
+0.8  Declared tests pass
+0.5  Compiler succeeds
+0.3  Patch applies cleanly
+0.2  Change is minimal
+0.1  Correct tool calls
+0.1  Successful error recovery
```

### Penalty Signals (Negative)
```
-0.5  Hallucinated APIs
-0.5  Invalid imports
-0.3  Broken builds
-0.3  False success claims
-0.2  Unnecessary rewrites
-0.2  Security regressions
-0.1  Repeated failed actions
-0.1  Excessive reasoning tokens
```

### Method
- GRPO (Group Relative Policy Optimisation) preferred
- Alternative: PPO with the reward model above
- Use TRL or OpenRLHF

### Exit Gate
- Test-pass rate improves on agentic benchmarks
- Tool-call correctness ≥ 98%
- Meaningful repair ability demonstrated
- No catastrophic regression

---

## Stage 6: Quantisation-Aware Optimisation

**Goal:** Ensure quality across all deployment quantisations.

### Quantisation Targets
| Format | Bits | Purpose |
|---|---|---|
| BF16 | 16 | Reference quality |
| Q8 | 8 | High-quality local |
| Q6_K | 6 | Near-lossless |
| Q5_K_M | 5 | Balanced |
| Q4_K_M | 4 | Default consumer |
| Q3_K_M | 3 | Constrained / Lite |

### Process
1. Quantise with llama.cpp
2. Evaluate each quantisation on the full benchmark suite
3. If Q4_K_M shows > 5% degradation on any primary metric, apply QAT
4. Produce MLX 4-bit conversion
5. Produce AWQ/GPTQ for GPU serving

### Exit Gate
- Q4_K_M within 5% of BF16 on HumanEval+
- Q4_K_M within 5% of BF16 on tool-call correctness
- All quantisations produce functional, loadable models
- Speed benchmarks recorded for all formats

---

## Data Scaling Plan

| Phase | CPT Tokens | SFT Examples | Verified Tasks | DPO Pairs | RL Tasks |
|---|---:|---:|---:|---:|---:|
| Pilot | 50M | 5,000 | 1,000 | 2,000 | — |
| Phase 2 | 250M | 20,000 | 5,000 | 10,000 | — |
| Phase 3 | 500M–1B | 50,000 | 15,000 | 30,000 | 5,000 |
| Phase 4 | 2–3B | 75,000 | 25,000 | 50,000 | 10,000 |

Proceed to the next phase only if the current phase shows measurable improvements.

---

*Amaura Labs — Building verifiable intelligence.*
