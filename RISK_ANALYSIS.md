# Risk Analysis & Mitigation Strategy (Amuara Labs)

## Overview

Deploying open-weight AI coding systems on consumer hardware involves technical, operational, data quality, and security risks. Below is the risk assessment and mitigation framework.

---

## Technical & Security Risk Matrix

| Risk Domain | Identified Risk | Impact Level | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Data Quality & Poisoning** | Synthetic dataset repetition or syntax flaws degraded model reasoning. | **HIGH** | Implemented `dataset_cleaner.py` with MinHash LSH deduplication, syntax filtering, and multi-domain manual validation. |
| **Hallucination & Invalid Code** | Model generates non-existent APIs or syntax errors. | **HIGH** | `SecurityAuditorAgent` and `ASTIndexer` validate symbol existence; `BenchmarkHarness` measures hallucination rate directly. |
| **VRAM / Out of Memory (OOM)** | Large context windows cause consumer GPU / Apple Silicon OOM crashes. | **MEDIUM** | Quantization via 4-bit NF4 Unsloth and GQA memory optimization limit VRAM usage to **1.18 GB**. |
| **Arbitrary Code Execution** | Running unverified generated test commands poses security risks to developer system. | **CRITICAL** | `SecurityAuditorAgent` scans for `eval`, `os.system`, and unsafe commands before test execution; sandboxed subprocess isolation. |
| **Overfitting on Small Benchmarks** | Model memorizes benchmark problems rather than learning software engineering principles. | **HIGH** | Evaluated on multi-domain real-world synthetic data across 10 technical domains (Backend, Distributed Systems, Compilers, etc.). |

---
