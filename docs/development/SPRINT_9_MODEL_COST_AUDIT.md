# Sprint 9 — Model Doctor, Adaptive Model Routing & Cost Governance Audit

## 1. Audit Overview

This document provides a comprehensive audit of all LLM providers, model selection logic, routing paths, fallback mechanisms, usage collection, cost accounting, budget enforcement, and escalation behaviors in Nexus CLI as of Sprint 9.

---

## 2. Active Provider Inventory

| Provider ID | Provider Name | Transport / API | Tool Support | Structured Output | Usage Metadata | Cost Metadata | Local / Remote | Privacy Class | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `hosted` | Hosted Provider (NVIDIA/OpenAI compatible) | HTTPS / OpenAI API | Yes | Yes (JSON) | Yes (tokens) | Estimated / Configured | Remote | `APPROVED_CLOUD` | Active |
| `nova` | Local Nova Backend (Ollama/PyTorch) | HTTP / Local REST | Yes (Guarded) | Yes (JSON) | Estimated (compute ms) | Zero API fee (Compute tracked) | Local | `LOCAL_ONLY` | Active |
| `custom` | Custom Hosted Model | OpenAI compatible | Configurable | Configurable | Yes (if returned) | Custom pricing | Remote / Private | `ANY_ALLOWED_PROVIDER` | Active |
| `router` | FallbackRouter Wrapper | Multiplexer | Min common | Min common | Aggregated | Aggregated | Hybrid | Inherited | Active |

---

## 3. Active Routing Paths & Roles

| Engineering Phase | Invocation Path | Current Model Selection Logic | Fallback Behavior | Cost & Budget Enforcement | Defect / Limitation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Task Interpretation & Planning** | `Planner`, `TwoNodeBackend` | Active model (`model_key`) or Ceiling model | Nova local fallback | Token limit check | Selected via model_key preference without task suitability probing |
| **Plan Criticism** | `Planner` | Active model | Nova fallback | Token limit check | Uses same model as planner |
| **Code Editing & Patching** | `ExecutionKernel`, `Session` | Active model | Nova fallback | `BudgetedClient` pre-call check | Retries charged against same run budget; no downshifting to local model for simple edits |
| **Debugging & Failure Repair** | `RepairLoop`, `RecoveryController` | Active model | Escalation requested | Recovery budget | Escalation wasn't previously backed by model capability probes |
| **Verification & Review** | `Verifier`, `TwoNodeBackend` | Ceiling / Verifier node | Deterministic local | Recorded in ledger | Independent review did not track exact token cost |

---

## 4. Usage Collection & Cost Accounting Audit

### 4.1 Token Accounting
- **Prompt Tokens**: Collected from provider-reported usage where available. Conservative byte-length estimation fallback used when missing.
- **Completion Tokens**: Collected from provider-reported usage or text length approximation (4 chars/token).
- **Cached Tokens**: Tracked when returned by provider API headers/metadata.

### 4.2 Cost Calculation
- Prices stored in `nexus/models.py` per million input/completion/cached tokens.
- Native billing currency: USD (`$`).
- Display currency: Configurable INR (`₹`) using canonical internal conversion rate (1 USD = 85 INR).

### 4.3 Budget Enforcement
- Hard ceilings enforced via `BudgetController` and `BudgetedClient`.
- Cost reservation before model execution prevents parallel or overrun overspending.
- Resumed runs restore spent cost; replanning preserves run ledger cost history.

---

## 5. Identified Defects & Migration Plan

1. **Defect**: Universal model score previously assumed rather than task-specific capability profiling.
   - **Migration**: Introduce `ModelDoctor` and `CapabilityProfile` with 6 probe dimensions (Protocol, Repository, Coding, Reasoning, Multi-file, Safety).
2. **Defect**: Uncontrolled provider escalation on environment or tool execution failures.
   - **Migration**: Introduce `ModelFailureAttribution` ensuring escalation triggers solely on model capability failure evidence.
3. **Defect**: Lack of explicit INR budget user flag and display currency formatting.
   - **Migration**: Add `--budget-inr` to CLI commands and multi-currency support in `CostLedger`.
4. **Defect**: No automated phase-specific downshifting from strong planning models to cheap execution models.
   - **Migration**: Implement phase-based adaptive routing in `ModelRouter`.
