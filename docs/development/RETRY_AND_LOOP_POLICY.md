# RETRY AND LOOP POLICY — NEXUS CLI

Nexus CLI prohibits blind retry of identical failed commands or strategies. Every recovery attempt requires new evidence, a modified context, a revised plan, or a different strategy.

---

## 1. Strategy Signatures

An `AttemptSignature` is computed from:
`SHA256(plan_version | strategy_type | model | selected_context_hash | target_files | patch_digest | command | repo_state_hash | failure_category)`

---

## 2. Loop Detection Rules

1. **Identical Strategy Repetition**: Same signature executed 2 consecutive times without new evidence → Block retry.
2. **Command Repetition on Unchanged State**: Command re-executed on unchanged repo state → Block execution.
3. **Oscillation**: Alternating between Strategy A and Strategy B repeatedly → Block and trigger plan revision or escalation.
4. **Context Expansion Limit**: 3 context expansions without new evidence → Stop context expansion.
5. **Replanning Limit**: 3 plan revisions per run → Exclude further replanning and escalate or terminate.

---

## 3. Recovery Budget Enforcement

| Budget Metric | Default Limit | Action on Exhaustion |
|---|---|---|
| Command Retries | 3 | Stop with `FAILED` or `BUDGET_EXHAUSTED` |
| Tool Retries | 5 | Stop with `FAILED` |
| Plan Revisions | 3 | Require user intervention |
| Context Expansions | 3 | Stop context expansion |
| Mutation Cycles | 5 | Rollback and terminate |
| Elapsed Time | 300 seconds | Terminate with `BUDGET_EXHAUSTED` |
