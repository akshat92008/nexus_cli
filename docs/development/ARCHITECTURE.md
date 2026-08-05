# Nexus CLI — Architecture Overview (Post-Sprint 9)

## 1. System Layers

1. **Governance & Verification Layer**: `nexus/verification.py`, `nexus/run_finalizer.py` (Fail-closed execution authority).
2. **Execution & Checkpoint Layer**: `nexus/execution/`, `nexus/mutation.py`, `nexus/sandbox.py` (Governed workspace mutation, rollback).
3. **Turn Coordination & Agent Layer**: `nexus/agent.py`, `nexus/pipeline.py`, `nexus/turn_coordinator.py` (Single event coordinator).
4. **Governed Tool Layer**: `nexus/tools.py`, `nexus/tool_executor.py`, `nexus/process_gateway.py` (Typed policy-controlled tools).
5. **Repository Intelligence & Context Engine**: `nexus/intelligence/repository/` (Canonical `RepositoryIntelligence` engine, AST symbol parsing, task-intent ranking).
6. **Planning & Task Decomposition**: `nexus/planner.py`, `nexus/plan_critic.py`, `nexus/plan_graph.py` (Structured plans, critic approval).
7. **Debugging & Failure Repair Intelligence**: `nexus/recovery/` (`FailureNormalizer`, `DiagnosisEngine`, `LoopDetector`, `StrategyRegistry`).
8. **Multi-File Engineering & Refactoring**: `nexus/multifile/` (`EngineeringChangeSet`, `ImpactAnalyzer`, `ChangeDependencyGraph`).
9. **Model Doctor, Adaptive Routing & Cost Governance**:
   - `nexus/models.py`: Authoritative `ModelRegistry` & `ModelDescriptor` with privacy classes and pricing.
   - `nexus/model_doctor.py`: Empirical `ModelDoctor` capability scorecard engine across 16 dimensions.
   - `nexus/model_router.py`: `ModelRouter` matching requirements to capabilities across 6 portfolio modes with phase downshifting.
   - `nexus/model_escalation.py`: `EscalationController` enforcing evidence-backed escalation.
   - `nexus/cost_accounting.py`: Canonical multi-currency `CostLedger` (USD & INR) and pre-call cost reservation.
   - `nexus/budget.py`: Hard ceiling `BudgetController` and `RunBudget` with `--budget-inr` support.
   - `nexus/provider_resilience.py`: Provider error normalizer and privacy policy enforcement.

---

## 2. Component Integration

```text
User Request
  ↓
ModelRouter (Portfolio Mode + Task Requirements + Privacy Policy)
  ↓
ModelDoctor (Capability Profile Check) -> Selects Cheapest Suitable Model Descriptor
  ↓
CostLedger (Atomic Pre-Call Cost Reservation) -> BudgetController (Hard Ceiling Check)
  ↓
LLM Call Invocation & Response Processing
  ↓
ProviderResilienceEngine (Error Normalization & Failure Attribution)
  ↓
CostLedger (Record Tokens, Native USD, Display INR, Artifact Persistence)
```
