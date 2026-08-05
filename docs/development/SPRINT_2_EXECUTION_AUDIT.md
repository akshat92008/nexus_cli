# Sprint 2: Execution Audit

## 1. Current Execution Flow
The current tool execution flow relies heavily on a monolithic `Agent` class. There is a `ToolExecutionController` in `nexus/tool_executor.py` which was introduced to centralize tool-lifecycle logic, but currently, its `execute` method merely delegates back to `Agent._execute_tool_with_safety`.

## 2. Command Execution Paths
Command execution happens primarily through the `ProcessExecutionGateway` (`nexus/process_gateway.py`).
- High-level requests are modeled as `ProcessRequest`.
- They are converted to `CommandSpec` and passed to a `SandboxRunner` (`nexus/sandbox.py`).
- The `SandboxRunner` enforces sandboxing using `bubblewrap` (Linux), `sandbox-exec` (macOS), or a restricted subprocess fallback. 
- Output is collected via daemon threads to prevent deadlocks and enforce `max_output_bytes`.

## 3. File Modification Paths
File mutation tools (`write_file`, `edit_file`, `patch_file`, `multi_edit`) are identified in `ToolExecutionController._MUTATION_TOOLS`. The schemas are defined in `nexus/tools.py`. However, file modifications do not uniformly capture original hash, size, and permissions before edit for deterministic rollback, although some undo tracking exists via `FileHistory`.

## 4. Tool Invocation Paths
Tool schemas are defined as plain dictionaries in `nexus/tools.py` (`TOOL_DEFINITIONS`). The agent invokes tools via `ToolExecutionController`, which provides pre/post execution hooks, network tagging, and capability checking. The results are largely primitive strings rather than structured results.

## 5. Error Handling
- Processes return a `CommandResult` object (containing exit code, stdout, stderr, timeout status). 
- Execution errors at the DAG level are handled by `nexus.runtime.kernel` (e.g., `TaskOutcome`, `classify_failure`). 
- Failures from tools are often just string messages instead of structured diagnostics that allow for programmatic recovery actions.

## 6. Retries & Timeouts
- Timeouts are strictly enforced at the subprocess level inside `SandboxRunner` (using `subprocess.TimeoutExpired`).
- Retries are mostly left to the autonomous agent loop or the DAG execution engine (`StepRepairer`), but lack a unified, risk-classified error recovery model.

## 7. State Management
- Workspace isolation is handled by `GitWorktreeSession` (`nexus/workspace.py`), which uses git worktrees or temporary copies to isolate concurrent sessions.
- Run state is tracked in files like `run_state.py` and `project_memory.py`, but a unified `RunState` that tracks every inspected/modified file and executed command for seamless resuming from an interruption needs to be robustly integrated.

## 8. Known Reliability Failures
- **Orphan/Zombie Processes:** Direct `subprocess.Popen` calls outside the gateway risk leaving zombie processes.
- **Unstructured Tool Returns:** Tools returning strings make it hard for the model to distinguish between command failure, timeout, or missing executables.
- **Monolithic Execution:** Too much execution logic is tied to the `Agent` class instead of a dedicated `ExecutionController`.
- **Silent Failures:** Subsystems occasionally swallow errors or fail to rollback workspaces correctly on severe crashes.
