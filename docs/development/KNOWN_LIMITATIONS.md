# KNOWN LIMITATIONS — SPRINT 10

## Subsystem Limitations
1. **Concurrency Ceiling**: Bounded by provider rate limits and local compute process limits. Max default concurrency set to 4 workers.
2. **Semantic Conflict Resolution**: Automatic resolution is supported for mechanical text conflicts. Architectural or semantic API conflicts block integration and require explicit orchestrator re-planning or human intervention.
3. **Unapproved Subprocess Execution**: Workers inside isolated workspaces cannot execute arbitrary unapproved system commands outside the policy-controlled tool gateway.
