# Nova v12 Foundation Bake-Off

## Purpose

Determine the strongest base model for Nova Code 4B through blind evaluation
on standardised prompts across all scoring dimensions.

## Candidates

| ID | Model | Params | Licence | Status |
|---|---|---|---|---|
| `nanbeige4.2-3b-base` | Nanbeige4.2-3B-Base | ~3B | Apache-2.0 | Lead candidate |
| `qwen2.5-coder-3b` | Qwen2.5-Coder-3B-Instruct | 3B | Apache-2.0 | Control |
| `phi-4-mini` | Phi-4-mini | 3.8B | MIT | Strong candidate |
| `qwen2.5-coder-7b` | Qwen2.5-Coder-7B-Instruct | 7B | Apache-2.0 | 8B variant candidate |

## Scoring Weights

| Dimension | Weight |
|---|---:|
| Code correctness | 25% |
| Debugging and repair | 15% |
| Repository task success | 15% |
| Tool use | 10% |
| FIM completion | 10% |
| Instruction following | 10% |
| Quantised performance | 5% |
| Speed and memory | 5% |
| Licence and ecosystem | 5% |

## Prompts

Located in `prompts/`:

| Category | File | Count |
|---|---|---:|
| Code generation | `code_generation.jsonl` | 20 |
| Debugging | `debugging.jsonl` | 10 |
| Repository editing | `repository_editing.jsonl` | 5 |
| Tool use | `tool_use.jsonl` | 5 |
| FIM completion | `fim.jsonl` | 10 |
| Instruction following | `instruction_following.jsonl` | 5 |

## How to Run

```bash
# Dry run — see what would be evaluated
python run_bakeoff.py --all-candidates --dry-run

# Run a single candidate
python run_bakeoff.py --candidate phi-4-mini

# Run all candidates
python run_bakeoff.py --all-candidates

# Score and generate report
python score_bakeoff.py --report --output results/bakeoff_report.md
```

## Rules

1. All candidates run on the **same hardware** with **same parameters**
2. Temperature is fixed at **0.0** (deterministic)
3. Max tokens is fixed at **2048**
4. Random seed is fixed at **42**
5. No candidate-specific prompt engineering
6. Results include raw outputs for inspection
7. The winner is determined by **weighted composite score**
8. If the gap is < 0.05, additional evaluation is required before committing

---

*Amaura Labs — Building verifiable intelligence.*
