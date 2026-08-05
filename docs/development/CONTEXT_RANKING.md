# Explainable Context Ranking Specification — Sprint 5

## 1. Overview

The Sprint 5 Context Ranking Engine (`nexus/intelligence/repository/ranking.py`) replaces arbitrary term-frequency heuristics with explainable, task-intent aware candidate ranking.

Every selected file, symbol, or excerpt includes a human-readable list of decision reasons (`reasons: list[str]`).

---

## 2. Intent Classification

Task descriptions are parsed into structured `TaskIntent` categories:
- `BUG_REPAIR`: Prioritizes failing stack trace files, impacted tests, and recent bug fixes.
- `FEATURE_IMPLEMENTATION`: Prioritizes target symbols, API routes, and components.
- `REFACTOR`: Prioritizes reverse dependency graph, callers, and interface definitions.
- `MIGRATION`: Prioritizes migration files, database schemas, and configuration contracts.
- `TEST_CREATION` / `TEST_REPAIR`: Prioritizes test fixtures, test files, and source definitions.
- `SECURITY_FIX`: Prioritizes high-risk authentication, permissions, and cryptographic files.
- `CONFIGURATION_CHANGE`: Prioritizes package manifests, environment configs, and CI workflows.

---

## 3. Scoring Weights & Signals

```text
Signal                                    Weight / Score
----------------------------------------  --------------
Explicit user reference                   +50.0
Failing stack trace match                 +40.0
Exact file path mention                   +35.0
Target monorepo package match             +20.0
Exact symbol match                        +15.0
Prioritized task-intent file type         +15.0 to +25.0
API route / DB model match                +12.0
Path term substring match                 +8.0
Symbol substring match                    +6.0
Git working tree modification             +5.0
Generated file penalty                    *0.2
Vendored directory penalty                *0.1
Unrelated monorepo package penalty        *0.1
```

---

## 4. Structured Rationale Output

Example explainable ranking output:
```json
{
  "path": "nexus/verification.py",
  "score": 45.0,
  "reasons": [
    "Filename matches task term: 'verification'",
    "Contains matching symbols: VerificationResult, finalize",
    "High-risk verification component"
  ],
  "estimated_tokens": 1250
}
```
