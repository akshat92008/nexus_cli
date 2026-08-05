# TASK CONTRACT SPECIFICATION

## Overview

The `TaskContract` is the authoritative, typed representation of an interpreted engineering request in Nexus CLI. It bridges the raw user prompt and structured repository context into a clear specification of objectives, requirements, constraints, assumptions, and risk.

---

## Data Schema

```python
class RequirementSource(str, Enum):
    EXPLICIT_USER = "explicit_user"
    REPOSITORY_EVIDENCE = "repository_evidence"
    INFERRED = "inferred"
    DEFAULT_POLICY = "default_policy"

class Requirement:
    id: str
    statement: str
    source: RequirementSource
    mandatory: bool
    evidence_reference: str | None

class Constraint:
    id: str
    description: str
    category: str  # e.g., architecture, security, backward_compatibility, scope
    is_prohibition: bool

class TaskContract:
    task_id: str
    raw_user_request: str
    normalized_objective: str
    task_type: TaskType
    repository_snapshot_id: str
    mandatory_requirements: list[Requirement]
    optional_requirements: list[Requirement]
    constraints: list[Constraint]
    prohibited_changes: list[Constraint]
    assumptions: list[Assumption]
    unresolved_questions: list[Question]
    risk_level: RiskLevel
    completion_definition: str
```

---

## Requirement Provenance Rules

1. **EXPLICIT_USER**: Stated directly in the prompt text. Must not be altered or omitted during planning or replanning.
2. **REPOSITORY_EVIDENCE**: Derived from test assertions, existing imports, schemas, or docstrings in the codebase.
3. **INFERRED**: Proposed by the LLM or heuristic interpreter based on task classification.
4. **DEFAULT_POLICY**: Mandated by Nexus engineering invariants (e.g., fail-closed verification, safety policies).
