# Nova Codex Model Files & Specifications

This directory contains the complete set of Ollama **Modelfiles** and specifications for the **Nova Codex** AI coding model family developed by Amaura Labs.

---

## 📁 Directory Structure & Modelfile Index

| File | Base Model Target | Description & Purpose | Format Protocol |
| :--- | :--- | :--- | :--- |
| [`Modelfile.nova_codex`](./Modelfile.nova_codex) | `./codex_nova` | **Production Standard for Nova Codex**. Features strict Junior Intern execution loop, exact casing matching, multi-file code generation, diff patching, and explanation/clarification fallback modes. | V11 Junior Intern (`<<THINKING>>`, `<<FILES>>`, `<<TEST_COMMAND>>`) |
| [`Modelfile.v11`](./Modelfile.v11) | `./codex_nova` | Full V11 production prompt format specification matching `Modelfile.nova_codex`. Used for production verification and deployment testing. | V11 Junior Intern |
| [`Modelfile.3b`](./Modelfile.3b) | `./nova3b-finetuned.gguf` | 3-Billion parameter variant Modelfile tuned for 4-bit quantized local execution. | Standard Junior Intern |
| [`Modelfile.amaura`](./Modelfile.amaura) | `./qwen2.5-coder-3b-instruct.Q4_K_M.gguf` | Baseline Amaura engine configuration with extended context parameters (4096 tokens) and sampling setup (`temperature 0.2`, `top_p 0.9`). | Basic Structured Format |
| [`Modelfile.eval`](./Modelfile.eval) | `./qwen2.5-coder-1.5b-instruct.Q4_K_M (1).gguf` | Minimal evaluation Modelfile for benchmark harness execution. | Raw ChatML |
| [`Modelfile.lastdance`](./Modelfile.lastdance) | `./last dance` | Special checkpoint tuned for high-fidelity multi-file patch generation and precise code diffs. | Multi-File Diff Patching |
| [`Modelfile.lasthope`](./Modelfile.lasthope) | `./lasthopemodel` | Strict format lock variant optimized for zero-hallucination code generation. | High-Precision Execution |
| [`Modelfile.nova345`](./Modelfile.nova345) | `./nova345` | Intermediate checkpoint specification with custom hyperparameter parameters. | Basic Structured Format |
| [`Modelfile.simple`](./Modelfile.simple) | `./nova3b-finetuned.gguf` | Streamlined prompt protocol with short monologues (≤50 words) for minimal context overhead. | Simplified Structured |
| [`Modelfile.nova3b11`](./Modelfile.nova3b11) | `./nova3b11` | Pure ChatML template setup for direct fine-tuning evaluation. | Raw ChatML |

---

## 🚀 Quick Start: Building & Deploying Models with Ollama

To deploy any of the Nova Codex model configurations locally using [Ollama](https://ollama.ai):

### 1. Primary Production Model (`nova_codex`)
```bash
# Build the production model
ollama create nova_codex -f modelfiles/Modelfile.nova_codex

# Run interactive CLI session
ollama run nova_codex "Write a Python script to sort a list of dictionaries by key."
```

### 2. Amaura 3B Engine Deployment (`nova3b`)
```bash
# Using the automated deployment script
chmod +x deploy.sh
./deploy.sh

# Or manually create from Modelfile.amaura
ollama create nova3b -f modelfiles/Modelfile.amaura
```

### 3. Verify Deployment
Run the automated verification suite to validate SHA256 checksums and prompt template compliance:
```bash
python3 verify_nova_codex_deployment.py
```

---

## 🎯 Format Protocol Overview

Nova Codex models adhere strictly to structured output tags for reliable downstream parsing by autonomous agents:

1. **`<<THINKING>>`**: Brief internal monologue (≤ 50 words) outlining the architectural approach and files affected.
2. **`<<FILES>>`**: Code blocks with explicit headers:
   ```python
   # filepath: src/solution.py
   # action: CREATE
   ```
   Or for code modifications:
   ```python
   # filepath: src/utils.py
   # action: MODIFY

   <<<<<<<
   [Original Code]
   =======
   [Updated Code]
   >>>>>>>
   ```
3. **`<<TEST_COMMAND>>`**: Shell test command (e.g. `pytest`, `go test ./...`, `npm test`).
4. **`<<RESPONSE>>`**: Used exclusively when plain-text explanations or summaries are requested instead of code.
5. **`<<CLARIFICATION>>`**: Triggered only if both the programming language and problem scope are underspecified.

---

## ⚡ Technical Specifications

- **Architecture:** Qwen 2.5 Coder Base / Fine-tuned GGUF Q4_K_M
- **Context Length:** 4,096 tokens (Default)
- **Stop Sequences:** `<|im_end|>`, `<|im_start|>`
- **Temperature:** `0.2` (Low variance, high precision execution)
