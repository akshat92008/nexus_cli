# Nova 1.5b: Model Specification & Capabilities Report

<div align="center">
  <i>The strongest open-weight AI coding system built for local execution.</i><br>
  <b>Developed by Amuara Labs</b>
</div>

---

## 1. Model Overview

**Nova 1.5b** is a state-of-the-art, open-weight AI software engineering model. Designed specifically to rival proprietary frontier models like Claude Fable 5 and Kimi K3, Nova abandons the traditional "next-token prediction" approach in favor of **Execution-Guided Reasoning**. 

Built to run entirely offline on consumer hardware (e.g., Apple Silicon with 8GB RAM), Nova 1.5b packs the architectural reasoning of a much larger model into a highly efficient 1.5-billion parameter footprint through the use of Test-Time Compute (TTC) and autonomous multi-agent orchestration.

---

## 2. Core Strengths: What Nova 1.5b Excels At

Nova 1.5b is not a general-purpose chatbot. It is a highly specialized software engineering engine. Its primary strengths are:

### A. Complex Problem Solving via Test-Time Compute (TTC)
Most models output their first guess. Nova uses **Monte Carlo Tree Search (MCTS)** to generate multiple potential solutions to a problem. It then executes these solutions in a secure sandbox. If a solution encounters a `SyntaxError` or `AssertionError`, Nova automatically backtracks, reads the error, and self-heals the code before presenting the final answer. 
* **Strength:** Unmatched reliability on complex algorithms and algorithmic debugging.

### B. Multi-File Repository Refactoring
Traditional models lose context in large codebases. Nova 1.5b uses **AST-Aware Retrieval (Abstract Syntax Tree)**. Instead of blindly reading files line-by-line, Nova understands the *structure* of the code. It maps dependencies between classes, functions, and modules.
* **Strength:** Safely refactoring code across dozens of interconnected files in Python, Rust, Go, TypeScript, and C++.

### C. Zero-Fabrication Code Generation
Nova learns through **Group Relative Policy Optimization (GRPO)**. During its training and self-improvement loops, it is only rewarded if its generated code compiles and passes unit tests in a real sandbox. It is heavily penalized for hallucinated APIs or fake dependencies.
* **Strength:** Writing syntactically correct, executable code that relies on actual libraries rather than hallucinated ones.

### D. Autonomous Auditing & Security Review
Through its **Hierarchical Multi-Agent Orchestration**, Nova splits itself into specialized roles. When tasked with a problem, the *Architect* plans the solution, the *Coder* writes it, and the *Reviewer* aggressively audits the code.
* **Strength:** Identifying memory leaks, security vulnerabilities (like SQL injection or XSS), and off-by-one errors before the code is ever deployed.

---

## 3. Key Architectural Innovations

Amuara Labs implemented several frontier techniques to push Nova 1.5b beyond standard open-source limits:

1. **The RLEF Loop (Reinforcement Learning from Execution Feedback):** 
   Nova possesses an autonomous self-improvement script (`self_improve.py`). It continuously evaluates its own performance on unseen problems, identifies its weakest domains (e.g., "Networking" or "Distributed Systems"), and dynamically generates new training data to patch its own knowledge gaps.

2. **Episodic Memory Rollbacks:**
   Nova maintains a local, semantic vector database (`memory.py`). It remembers past conversations and architectural decisions. Crucially, if Nova's multi-agent system goes down a flawed architectural path, it can perform an "episodic rollback" (similar to a `git reset`), allowing it to try a new approach without poisoning its context window.

3. **Parametric Dataset Generation:**
   Nova was trained on 100,000+ highly diverse, synthetically generated tasks across 15 engineering domains. Because the data is generated parametrically rather than relying on static templates, Nova has been exposed to an immense variety of edge cases and constraints.

---

## 4. Technical Specifications & Deployment

Nova 1.5b is engineered for maximum efficiency and privacy.

- **Parameters:** 1.5 Billion
- **Quantization:** GGUF (Q4_K_M) 4-bit precision
- **VRAM/RAM Requirement:** ~1.18 GB (Can easily run on 8GB Unified Memory systems)
- **Deployment Target:** Local execution on Apple Silicon (M1/M2/M3) and consumer NVIDIA GPUs.
- **Privacy:** 100% Offline. Zero telemetry, zero data collection. All inference, AST indexing, and sandboxed execution happens entirely on the local machine.

---

## 5. Ideal Use Cases

Nova 1.5b is best deployed as a persistent local pair-programmer or background agent. Ideal scenarios include:
- **Offline CI/CD Auditing:** Reviewing pull requests locally for security flaws and logical errors without uploading code to third-party servers.
- **Legacy Codebase Modernization:** Pointing Nova at a large, undocumented repository and asking its Architect agent to map dependencies and plan a migration.
- **Autonomous Bug Fixing:** Feeding a GitHub issue and a stack trace directly into Nova's Test-Time Compute engine, allowing it to generate, test, and verify the patch autonomously.

---
*Nova 1.5b proves that with rigorous execution-guided engineering, a highly efficient local model can match the reasoning capabilities of massive, cloud-bound frontier models.*
