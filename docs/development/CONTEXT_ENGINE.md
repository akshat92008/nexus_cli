# Context Engine Architecture & Data Flow — Sprint 5

## 1. Overview

The Sprint 5 Context Engine (`nexus/intelligence/repository/engine.py`) provides intelligent context selection, candidate ranking, secret redaction, token budgeting, and evidence-driven context expansion loops for Claude Code-level repository comprehension.

---

## 2. Core Modules

| Module | File | Responsibility |
| :--- | :--- | :--- |
| **Model** | `nexus/intelligence/repository/model.py` | Canonical typed dataclasses (`RepositorySnapshot`, `ContextBundle`, `TaskIntent`) |
| **Discovery** | `nexus/intelligence/repository/discovery.py` | Root/Git discovery, ecosystem detection, file walking, tree-hash calculation |
| **Classification** | `nexus/intelligence/repository/classification.py` | Categorization (`source`, `test`, `config`, `migration`, `secret_sensitive`) |
| **Extraction** | `nexus/intelligence/repository/extraction.py` | Language-aware AST & parser symbol/dependency extraction |
| **Secrets** | `nexus/intelligence/repository/secrets.py` | Secret token detection & redaction |
| **Ranking** | `nexus/intelligence/repository/ranking.py` | Task-intent classification & explainable scoring |
| **Budget** | `nexus/intelligence/repository/budget.py` | Token budget management & line-numbered excerpt generation |
| **Engine** | `nexus/intelligence/repository/engine.py` | High-level `RepositoryIntelligence` coordinator |

---

## 3. Data Flow

```text
User / Task Input
  ↓
TaskIntent Classifier (Bug, Feature, Refactor, Security, Config, etc.)
  ↓
Repository Snapshot & Tree Hash Check
  ↓
Candidate Generation (Symbols, Error traces, Imports, Tests, Config, Git changes)
  ↓
Explainable Ranking Engine (Score + Reasons + Monorepo Scoping)
  ↓
Secret Protector (Redacts API keys, credentials, .env values)
  ↓
Context Budget Manager (Excerpt range extraction, token budgeting, line numbers)
  ↓
Typed ContextBundle Prompt Formatting -> Sent to LLM Model
```

---

## 4. Evidence-Driven Context Expansion Loop

When the model or planner detects missing dependencies or unresolved symbols:
1. `engine.expand_context(bundle, reason="Missing token verification details", additional_files=["auth.py"])` is invoked.
2. The engine re-queries the candidate ranker with expanded file constraints.
3. The budget is adjusted to accommodate additional decisive context.
4. The expanded `ContextBundle` is returned with updated version identity.
