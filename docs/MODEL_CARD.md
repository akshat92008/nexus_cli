# Nova v12 — Model Card Template

## Model Details

### Model Name
amauralabs/Nova-Code-4B

### Model Version
v12.0

### Model Type
Causal Language Model — Code Generation, Debugging, Completion, Editing, Agentic

### Foundation Model
[To be determined by bake-off]

### Developed By
Amaura Labs

### Licence
[Foundation licence] + Amaura Labs derivative terms

### Model Date
[Release date]

---

## Intended Use

### Primary Use Cases
- Code generation across 9+ programming languages
- Fill-in-the-middle (FIM) code completion for IDE integration
- Code debugging and repair from error messages and test failures
- Repository-level code editing with minimal patches
- Agentic multi-turn tool use for software engineering tasks
- Code review, explanation, and refactoring

### Target Hardware
- 8 GB consumer laptops and desktops (Q4_K_M quantisation)
- Apple Silicon Macs (MLX 4-bit)
- NVIDIA GPUs (BF16 or quantised)
- CPU-only inference (GGUF)

### Out-of-Scope Uses
- Medical, legal, or financial advice
- Generating malicious code
- Replacing human code review for safety-critical systems
- Claims of frontier-model capability

---

## Training Data

### Continued Pretraining
- [X] billion tokens of permissively licensed source code
- Languages: Python, JavaScript, TypeScript, Java, C++, Go, Rust, SQL, Bash
- Sources: Permissively licensed repositories (MIT, Apache-2.0, BSD)
- All data filtered for: licence compliance, secrets, PII, malware, benchmark contamination

### Supervised Fine-Tuning
- [X] examples across [X] operating modes
- All examples execution-verified (compile + test)

### Preference Data
- [X] execution-ranked preference pairs
- Ranking based on: compilation success, test results, change minimality

### Agentic Trajectories
- [X] tool-use trajectories
- Tools: file operations, search, patch application, test execution

### Dataset Card
See [DATASET_CARD.md](DATASET_CARD.md) for full data provenance.

---

## Evaluation Results

### Code Generation

| Benchmark | Nova Code 4B (BF16) | Nova Code 4B (Q4_K_M) | Foundation Base |
|---|---|---|---|
| HumanEval+ | | | |
| MBPP+ | | | |
| LiveCodeBench | | | |
| BigCodeBench | | | |

### Repository & Editing

| Benchmark | Nova Code 4B | Foundation Base |
|---|---|---|
| RepoBench | | |
| SWE-bench Lite | | |

### Agentic & Tool Use

| Metric | Nova Code 4B |
|---|---|
| Tool-call correctness | |
| Multi-turn repair success | |

### Completion (FIM)

| Metric | Nova Code 4B |
|---|---|
| FIM exact match | |
| Post-completion compilation rate | |

### Local Performance

| Metric | Q4_K_M | Q8 | BF16 |
|---|---|---|---|
| Tokens/second | | | |
| Time to first token | | | |
| Peak memory (GB) | | | |

---

## Limitations

- [List honest limitations discovered during evaluation]
- [List languages/frameworks with weak performance]
- [List known failure modes]
- [List hallucination patterns]

---

## Ethical Considerations

- Model may generate code with security vulnerabilities
- Model may reproduce patterns from training data
- Model should not be used as sole reviewer for safety-critical code
- All training data is permissively licensed with tracked provenance

---

## How to Use

### Ollama
```bash
ollama run amauralabs/nova-code
```

### Transformers
```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained("amauralabs/Nova-Code-4B")
tokenizer = AutoTokenizer.from_pretrained("amauralabs/Nova-Code-4B")
```

### llama.cpp
```bash
./llama-cli -m Nova-Code-4B-Q4_K_M.gguf -p "<|nova_code|>\nWrite a Python rate limiter..."
```

---

## Citation

```bibtex
@misc{amaura2025novacode,
  title={Amaura Nova Code: A Local-First Coding Model Family},
  author={Amaura Labs},
  year={2025},
  url={https://huggingface.co/amauralabs/Nova-Code-4B}
}
```

---

*Amaura Labs — Building verifiable intelligence.*
