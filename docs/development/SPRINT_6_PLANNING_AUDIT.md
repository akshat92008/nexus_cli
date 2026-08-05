# SPRINT 6 — PLANNING SYSTEM AUDIT

## 1. Overview

This document provides a comprehensive audit of all planning, task-decomposition, intent-classification, and plan-handling paths within the Nexus CLI codebase prior to Sprint 6 canonical consolidation.

---

## 2. Planning Path Inventory

| Path Name | Entry Point | Type (Model / Deterministic) | Context Input | Output Type | Validator | Critic | Approval Flow | Execution Consumer | Current Defects | Migration Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| `PlanningEngine` | `nexus/planner.py` | Hybrid (Heuristic + LLM) | Raw task string + repo context | `ExecutionPlan` / `PlanStep` | Basic field checks | None (self-approved) | Interactive / Auto | `pipeline.py`, `agent.py` | Free-form markdown steps, unverified completion conditions, missing explicit caller analysis | **Retain & Extend** as frontend wrapper for `nexus/planning/` |
| `TwoNodeBackend.decompose` | `nexus/two_node_backend.py` | LLM-driven | `planner_context` + user request | `list[AtomicTask]` | Basic schema parse | None | Internal | `TwoNodeBackend.run` | Provider-specific schema, bypassing canonical criteria | **Migrate** to `nexus/planning/` contracts |
| `NovaRuntime.plan` | `nexus/nova_runtime.py` | LLM / Heuristic | Nova prompt + file list | `NovaPlan` | None | None | Auto | `nova_runtime.py` | Unbounded scope, missing rollback strategy | **Migrate** to `nexus/planning/` execution contract |
| `Agent._active_plan` | `nexus/agent.py` | Model-driven | `get_plan_context()` | `ExecutionPlan` | None | Self | Auto / Command | `Agent.run_turn` | Mutation begins before formal plan validation | **Enforce** canonical `ExecutionContract` before mutation |
| `LeadOrchestrator.decompose` | `nexus/collaboration/lead_orchestrator.py` | Model-driven | Shared task context | `list[SubTask]` | Internal validator | None | Orchestrator approval | Collaboration subagents | Duplicate decomposition logic, inconsistent criteria | **Migrate** to canonical task & graph engine |
| `BenchmarkPlanner` | `nexus/benchmark.py` | Model-driven | Benchmark prompt | Free-form dict | None | None | Auto | `benchmark.py` | Ad-hoc evaluation without typed contract | **Unify** with `nexus/benchmarks/benchmark_planning.py` |

---

## 3. Active Planning Paths & Defect Analysis

### 3.1 `nexus/planner.py`
- **Entry Points**: `PlanningEngine.analyze()`, `PlanningEngine.create_plan()`, `PlanningEngine.advance_step()`.
- **Defects Identified**:
  1. Steps often contain free-form prose without machine-verifiable completion conditions.
  2. Missing dedicated critic stage; planner approves its own generated plans.
  3. Lack of explicit caller graph or reverse-dependency blast-radius analysis before scope definition.
  4. Replanning overwrites existing plan state without retaining structured version lineage (`plan-v1`, `plan-v2`).

### 3.2 `nexus/two_node_backend.py`
- **Entry Points**: `TwoNodeBackend.decompose()`, `TwoNodeBackend._execution_plan()`.
- **Defects Identified**:
  1. Uses provider-specific task decomposition incompatible with canonical `TaskContract`.
  2. Bypasses deterministic scope validation and policy checks.

### 3.3 `nexus/agent.py` & `nexus/pipeline.py`
- **Entry Points**: Direct turn loop execution.
- **Defects Identified**:
  1. Code mutations can occasionally start before formal plan validation completes.
  2. Acceptance criteria generation relies on heuristics without explicit link to executable test verification strategies.

---

## 4. Migration Strategy

1. Create unified `nexus/planning/` subsystem containing:
   - Canonical `TaskContract` (`nexus/planning/task_contract.py`)
   - Canonical `EngineeringPlan` (`nexus/planning/engineering_plan.py`)
   - Ambiguity & Clarification Engine (`nexus/planning/ambiguity.py`)
   - Acceptance Criteria Engine (`nexus/planning/acceptance.py`)
   - Deterministic Validator & Dependency Graph (`nexus/planning/validator.py`, `nexus/planning/graph.py`)
   - Blast-Radius & Scope Estimator (`nexus/planning/scope.py`)
   - Risk & Cost Estimator (`nexus/planning/risk.py`, `nexus/planning/cost.py`)
   - Independent Plan Critic (`nexus/planning/critic.py`)
   - Runtime Execution Contract (`nexus/planning/execution_contract.py`)
   - Lineage-Preserving Replanner (`nexus/planning/replanner.py`)
   - Extensible Planning Policies (`nexus/planning/policies.py`)
2. Wrap `nexus/planner.py` to delegate to `nexus/planning/` while preserving backward compatibility.
3. Update `nexus/agent.py`, `nexus/pipeline.py`, `nexus/two_node_backend.py`, and `nexus/nova_backend.py` to consume canonical execution contracts.
