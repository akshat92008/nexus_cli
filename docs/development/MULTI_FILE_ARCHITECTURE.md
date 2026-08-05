# Multi-File Engineering Architecture (`nexus.multifile`)

## Architectural Principles

1. **Transactional Change Sets**: Multi-file edits are never treated as independent single-file modifications. Every multi-file operation is captured in a canonical `EngineeringChangeSet`.
2. **Impact-Aware Planning**: Proposed contract changes are analyzed by `ImpactAnalyzer` to discover all direct callers, reverse imports, test targets, and configuration references before code mutation begins.
3. **Deterministic Validation**: `ChangeSetConsistencyValidator` enforces 8 pre-verification checks (reasons for inclusion, protected paths, generated source protection, caller completeness, import validity, schema migrations, package structure, and test coverage).
4. **Dependency-Ordered Execution**: `ChangeDependencyGraph` uses Kahn's algorithm for topological sorting and detects cycles or symbol conflicts.
5. **Bounded Staging & Checkpoints**: `StagedChangeSetExecutor` executes changes in bounded stages. Each stage creates a checkpoint, runs intermediate verification commands, and enforces mandatory gate pass criteria.
6. **Bounded Recovery**: `MultiFileRecoveryHandler` classifies stage failures, performs stage-level or full rollback, and handles missed callers via bounded scope expansion (maximum 3 expansions).

```
 ┌────────────────────────────────────────────────────────┐
 │                 EngineeringChangeSet                   │
 └───────────────────────────┬────────────────────────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   ┌─────────────────┐               ┌─────────────────┐
   │ ImpactAnalyzer  │               │ ConsistencyVal  │
   └────────┬────────┘               └────────┬────────┘
            │                                 │
            └────────────────┬────────────────┘
                             ▼
               ┌───────────────────────────┐
               │  ChangeDependencyGraph    │
               │   (Topological Order)     │
               └─────────────┬─────────────┘
                             ▼
               ┌───────────────────────────┐
               │  StagedChangeSetExecutor  │
               │ (Checkpoints & Verifier)  │
               └─────────────┬─────────────┘
                             ▼
               ┌───────────────────────────┐
               │  MultiFileRecoveryHandler │
               │   (Rollback & Expansion)  │
               └───────────────────────────┘
```
