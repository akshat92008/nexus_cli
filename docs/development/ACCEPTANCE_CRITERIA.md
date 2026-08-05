# ACCEPTANCE CRITERIA SPECIFICATION

## Overview

In Nexus CLI, acceptance criteria are executable contracts that define what success means for a given task before code mutation begins.

---

## Data Model

```python
class VerificationType(str, Enum):
    COMMAND = "command"        # Shell command execution (e.g. pytest)
    FILE_EXISTS = "file_exists"  # File existence check
    SYMBOL_PRESENT = "symbol_present" # AST symbol lookup
    POLICY = "policy"          # Safety / architecture rule check

class VerificationStrategy:
    type: VerificationType
    command_intent: str | None
    target_path: str | None
    expected_output: str | None

class AcceptanceCriterion:
    id: str
    requirement_source: str
    statement: str
    mandatory: bool
    verification: VerificationStrategy
    affected_scope: list[str]
    status: str  # PENDING, SATISFIED, FAILED
```

---

## Validation Invariants

1. Every `mandatory` requirement in the `TaskContract` must map to at least one `AcceptanceCriterion`.
2. Vague statements such as "works properly" or "clean implementation" are rejected.
3. Every criterion must specify a deterministic verification strategy.
4. Acceptance criteria persist across replanning iterations.
