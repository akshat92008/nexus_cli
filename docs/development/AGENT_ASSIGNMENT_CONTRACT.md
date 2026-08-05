# AGENT ASSIGNMENT CONTRACT

## Overview
The `AgentAssignment` contract defines the explicit, bounded, and typed unit of work given to any worker agent in Nexus CLI.

## Contract Structure
```python
class AgentAssignment:
    assignment_id: str
    role: AgentRole
    objective: str
    parent_plan_step_ids: list[str]
    repository_snapshot_id: str
    context_bundle_id: str
    allowed_read_paths: list[str]
    allowed_mutation_paths: list[str]
    protected_paths: list[str]
    dependencies: list[str]
    acceptance_criteria: list[str]
    expected_deliverables: list[str]
    allowed_tools: list[str]
    model_requirements: dict
    model_id: str | None
    budget: WorkerBudget
    timeout_seconds: int
    retry_limit: int
```

## Status Values
- `COMPLETED`: Worker finished assignment with real patch or evidence.
- `LOCALLY_VALIDATED`: Worker-local validation passed (never equals task-level `VERIFIED`).
- `PARTIALLY_COMPLETED`: Partial deliverables produced.
- `BLOCKED`: Dependency or permission blocker encountered.
- `FAILED`: Failure during execution.
- `CANCELLED`: Cancelled by orchestrator.
- `TIMED_OUT`: Timeout threshold exceeded.
