# PLAN CRITIC SPECIFICATION

## Overview

The `PlanCritic` is an independent evaluation stage that challenges initial engineering plans before execution contract generation. The critic is logically separate from the initial plan generator to prevent confirmation bias and self-approval.

---

## Evaluation Categories

1. **Root Cause & Hypothesis Validity**: Are candidate root causes backed by empirical trace/test evidence?
2. **Caller & Interface Graph Analysis**: Did the plan account for all reverse dependencies and function call sites?
3. **Test Strategy Completeness**: Does the plan include both targeted verification and regression checks?
4. **Scope & Blast-Radius**: Does the plan propose broad rewrites for narrow bugs or modify protected files?
5. **Architecture Boundaries**: Does the plan violate layer boundaries or introduce circular imports?
6. **Backward Compatibility & Migrations**: Are API changes properly versioned or backward-compatible?
7. **Rollback Strategy**: Is a clear rollback boundary defined for high-risk or multi-file mutations?

---

## Critique Decisions

- `APPROVE`: The plan is sound, well-bounded, and fully verifiable.
- `APPROVE_WITH_WARNINGS`: Minor non-blocking risks identified; execution can proceed with caution.
- `REVISE`: Blocking flaws identified (missing tests, invalid file paths, dependency cycle). Plan must be revised.
- `BLOCK`: Unsafe request or policy violation. Plan execution is rejected.
