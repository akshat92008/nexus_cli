# Sprint 3: Architecture Audit

## Current Architecture

The current architecture revolves heavily around the `Agent` class in `nexus/agent.py`. Based on the imports and class structure, the `Agent` class acts as a monolithic "god object" that orchestrates everything:
- Execution and state management
- Context gathering
- Planning (`PlanningEngine`)
- Verification (`VerificationEngine`)
- Subprocess execution and Sandboxing (`sandbox.py`)
- Tool execution (`execute_tool`)
- Recovery, history, memory, logging
- Provider integrations (`HostedProvider`, `NovaProvider`, etc.)

**Entry Points:**
- `cli.py` invokes the agent.
- `Agent` class is instantiated and used to run the main loop.

**Major Classes:**
- `Agent`: The monolithic orchestrator.
- `PlanningEngine`: Handles planning but might be too tightly coupled with Agent.
- `VerificationEngine`: Handles verification.
- `ExecutionController` / `RunFinalizer` (from Sprint 2).

**Identified Architecture Problems:**

1. **God Classes:**
   - The `Agent` class handles planning, execution, verification, state management, provider selection, CLI output, and file editing tools directly. It lacks single responsibility.

2. **Mixed Responsibilities:**
   - Planner might be executing commands instead of just planning.
   - Verification might be deeply tied to mutation.
   - Tools decide success instead of a centralized VerificationController.
   - CLI logic intertwined with Agent lifecycle.

3. **Duplicate Systems:**
   - Multiple providers (`HostedProvider`, `NovaProvider`, `openai_compat.py`) scattered.
   - Execution pathways scattered across `sandbox.py`, `tools.py`, `execution.py`.
   - Workspace session logic scattered (`GitWorktreeSession`, `ContextManager`, etc.).

4. **Circular Dependencies:**
   - Agent imports tools, tools import state, state imports agent, etc.

5. **Configuration Sprawl:**
   - Lack of a central `NexusConfig`. Env vars, default values, and project configs are scattered.

## Next Steps
We need to modularize this into distinct Controllers (Session, Planning, Context, Execution, Mutation, Verification, Recovery, Evidence, Finalizer) and decouple the Agent class.
