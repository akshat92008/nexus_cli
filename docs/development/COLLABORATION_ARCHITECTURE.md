# COLLABORATION ARCHITECTURE

## Overview
Nexus CLI multi-agent collaboration provides a production runtime for parallel and specialized engineering agents to work on software tasks without duplicating effort, corrupting state, losing context, creating incompatible patches, or falsely claiming completion.

## Key Principles
1. **Optional, Not Default**: Multi-agent execution is triggered only when task structure and budget provide a measurable advantage. Small or tightly coupled tasks default to single-agent execution.
2. **Canonical Contract**: All workers operate from a shared task contract, plan version, snapshot revision, and explicit allowed scopes.
3. **Workspace Isolation**: Mutating workers execute in isolated Git worktrees or temporary workspace copies. The live main workspace is protected.
4. **Real Patch Integration**: Patch artifacts are validated, applied to an integration workspace tree, conflict-checked, and verified via tree hash calculation.
5. **Independent Central Verification**: Final `VERIFIED` status is granted only by canonical central verification on the exact integrated repository tree. Workers cannot issue task-level `VERIFIED`.

## Modes
- `SINGLE_AGENT`: Single model execution for trivial or coupled tasks.
- `REVIEW_PAIR`: One implementer + one independent reviewer.
- `SPECIALIST_TEAM`: Implementer + Test Engineer + Security/Architecture Reviewers.
- `PARALLEL_ANALYSIS`: Independent read-only investigation streams.
- `PARALLEL_IMPLEMENTATION`: Parallel mutating workers on non-overlapping package boundaries.
- `STAGED_COLLABORATION`: Sequential dependency stages with review gates.
