# SPRINT 7 — RECOVERY SYSTEM AUDIT

This document audits all active retry, repair, debugging, fallback, and error-handling mechanisms in Nexus CLI prior to Sprint 7 consolidation.

---

## 1. Executive Summary

Prior to Sprint 7, failure handling was fragmented across several modules (`nexus/agent.py`, `nexus/repair.py`, `nexus/runtime/kernel.py`, `nexus/pipeline.py`, `nexus/planner.py`, `nexus/two_node_backend.py`, and `nexus/providers/provider_manager.py`).

Key findings of the audit:
1. **Blind Retries**: Early loops (e.g. `RepairLoop` in `nexus/repair.py`) used fixed iteration counters without detecting whether the attempt strategy or patch content had changed.
2. **Missing Rollback on Failure**: Failed mutations in interactive or two-node runs were sometimes preserved without verifying workspace integrity, leading to dirty intermediate state.
3. **Coarse Failure Classification**: Classification relied on simple regex keyword matching (`classify_failure`) rather than normalized structured records distinguishing root causes from symptoms or environmental blockers.
4. **Lack of Loop Prevention**: Identical tool calls or repeated failing patches could be executed multiple times without stopping or escalating.
5. **Resetting Budgets**: Replanning or multi-turn execution did not persist unified recovery budgets across iterations.
6. **Disjointed Recovery Path**: Multiple legacy paths (`RepairLoop`, `TaskDagKernel` repairs, provider retries, two-node fallback) operated independently without routing through a single authoritative controller.

All recovery paths are consolidated in Sprint 7 into the canonical `RecoveryController` (`nexus/recovery/controller.py`).

---

## 2. Recovery Path Inventory Table

| ID | Path Name | Entry Point | Trigger | Failure Classification | Strategy Selection | Rollback Behavior | Migration Decision |
|---|---|---|---|---|---|---|---|
| RP-01 | Autonomous Repair Loop | `nexus.repair.RepairLoop.run` | Failed test/mutation in turn | `FailureKind` regex | Keyword template prompt | Optional post-run | Consolidated into `RecoveryController` |
| RP-02 | Task DAG Step Repair | `nexus.runtime.kernel.TaskDagKernel._run_step` | Step failure / verifier rejection | `classify_failure` regex | Generic repair callback | Checkpoint per step | Migrated to `RecoveryController` |
| RP-03 | Two-Node Fallback | `nexus.two_node_backend.TwoNodeBackend.execute` | Local model failure | None | Fallback to cloud provider | None | Governed by `RecoveryController` |
| RP-04 | Provider API Retry | `nexus.providers.provider_manager.ProviderManager` | HTTP rate limit / 5xx | Provider error code | Exponential backoff | None | Retained for transport layer only |
| RP-05 | Structured Output Repair | `nexus.planner.ExecutionPlanner` | JSON schema parsing error | Schema error | Prompt re-formatting | None | Consolidated into `RecoveryController` |
| RP-06 | Verification Repair Loop | `nexus.run_finalizer.RunFinalizer` | Verification check failed | Check output | Additional repair prompt | Rollback if verified fails | Consolidated into `RecoveryController` |
| RP-07 | Command Execution Retry | `nexus.tool_executor.ToolExecutor` | Process timeout/error | Exit code / timeout | Re-run command | None | Governed by `RecoveryController` |
| RP-08 | Workspace Rollback | `nexus.recovery.RollbackManager` | User command / manual trigger | None | Undo file history | File history undo | Retained & integrated into `RecoveryController` |

---

## 3. Detailed Path Audits

### RP-01: Autonomous Repair Loop (`nexus/repair.py`)
- **Entry Point**: `RepairLoop.run(original_prompt, failure_context)`
- **Trigger**: Test or verification failure after model turn.
- **Failure Input**: Exception string, stderr, or test failure message.
- **Classification**: Keyword matching into `FailureKind` enum (`SYNTAX`, `IMPORT`, `TYPE`, `TEST`, etc.).
- **Strategy Selection**: Selects hardcoded prompt templates.
- **Retry Limits**: Default 3 iterations, 120s budget.
- **Rollback Behavior**: None during loop iterations; workspace retained even if repair failed.
- **Defects**: Does not verify if the patch changed; allows identical failed strategies; does not update execution plan; does not track cost or attempt signatures.
- **Migration Decision**: Replaced with `RecoveryController.run_repair_loop()`.

### RP-02: Task DAG Step Repair (`nexus/runtime/kernel.py`)
- **Entry Point**: `TaskDagKernel._run_step()`
- **Trigger**: `TaskOutcome.success == False`.
- **Classification**: `classify_failure(outcome.output)`.
- **Strategy Selection**: Calls `repair(step, outcome, failure_kind, repair_number)`.
- **Retry Limits**: `step.retry_limit` and `max_total_repairs`.
- **Rollback Behavior**: Restores task checkpoint on failure.
- **Defects**: No loop signature detection; replanning is not automatically triggered on root-cause changes.
- **Migration Decision**: Delegate step repair decisions to `RecoveryController`.

### RP-03: Two-Node Fallback (`nexus/two_node_backend.py`)
- **Entry Point**: `TwoNodeBackend.execute()`
- **Trigger**: Local model output failure or tool error.
- **Classification**: Primitive exception check.
- **Strategy Selection**: Switch node from primary (local) to secondary (cloud).
- **Retry Limits**: Single fallback attempt.
- **Rollback Behavior**: None.
- **Defects**: Does not log structured failure evidence or record model escalation reasoning.
- **Migration Decision**: Model escalation recommendations route through `RecoveryController`.

---

## 4. Legacy Code Consolidation Plan

1. Create `nexus/recovery/` package with authoritative `RecoveryController`.
2. Wrap or update `RepairLoop` in `nexus/repair.py` to route through `RecoveryController`.
3. Update `ExecutionKernel` and `TaskDagKernel` in `nexus/runtime/kernel.py` to use `RecoveryController`.
4. Route agent failure handling in `nexus/agent.py` through `RecoveryController`.
5. Update `nexus/pipeline.py` and `nexus/cli.py` to expose structured recovery events, status, and commands (`nexus run status/failures/resume/rollback`).
