# SPRINT 4 TOOL AUDIT

This document records the audit of the current tool execution architecture in Nexus, assessing how tools are registered, validated, authorized, and executed.

## Tool Path Inventory

| Tool Name / Category | Public/Internal | Mutating/Read-Only | Process Exec | Network | Approval | Canonical Handler | Current Problems | Intended Migration |
|---|---|---|---|---|---|---|---|---|
| `read_file`, `file_info`, `diff_files`, `list_directory`, `find_files`, `get_project_structure` | Public | Read-Only | No | No | No | `tools.py` via `RAW_TOOL_DEFINITIONS` | Uses `dict` schemas instead of typed `ToolDefinition`. Returns `str` instead of `ToolResult`. | Migrate to typed `ToolDefinition` and `ToolResult`. |
| `write_file`, `edit_file`, `patch_file`, `multi_edit` | Public | Mutating | No | No | Yes (Safety Check) | `tools.py` via `RAW_TOOL_DEFINITIONS` | Validation happens deep inside `agent.py:_execute_tool_with_safety_impl`. | Move safety and bounds checking to `ToolExecutionController`. |
| `run_command`, `process_run`, `process_status`, `process_stop` | Public | Mutating | Yes | Tagged (Regex) | Conditional | `sandbox.py` (via `tools.py`) | Network tagging relies on fragile regex in `agent.py`. Bypasses structured permissions. | Define `requires_network` and `permission` in `ToolDefinition`. |
| `git_status`, `git_diff`, `git_commit`, `git_log`, `git_branch` | Public | Mutating/Read | Yes | No | Conditional | `tools.py` | Shell commands run via `subprocess` directly in handlers or `workspace.py`. | Standardize through safe `subprocess` wrappers in `sandbox.py`. |
| `web_fetch`, `web_search` | Public | Read-Only | No | Yes | No | `tools.py` | Network intent tracked manually in `agent.py`. | Explicit `requires_network` flag. |
| `repo_index`, `repo_symbols`, `repo_impact`, `repo_context` | Public | Read-Only | No | No | No | `tools.py` | Relies on legacy dictionary dispatch. | Formalize as `ToolDefinition`. |
| Internal `subprocess.run` (e.g., `workspace.py`) | Internal | Mutating | Yes | Variable | No | `workspace.py` | Direct shell invocations bypassing `sandbox` and `execution_controller`. | Centralize Git/Command execution through a safe internal API. |

## Audit Findings

### 1. `ToolDefinition` and `ToolResult` vs `RAW_TOOL_DEFINITIONS`
- `tools.py` defines a `ToolDefinition` class, but the system actually relies on a massive list of raw dictionaries (`RAW_TOOL_DEFINITIONS`) to define tools for the model. 
- The `execute_tool` function simply looks up a handler in a `TOOL_DISPATCH` dictionary and returns a raw string. 
- There is no uniform `ToolResult` returned from the handlers, violating the structured evidence requirement.

### 2. The God Object: `agent.py`
- `agent._execute_tool_with_safety_impl` is a massive 200+ line function.
- It manually hardcodes which tools are "mutation_tools" and "read_tools".
- It uses fragile regular expressions to detect network commands (`curl`, `pip install`, `git push`, etc.) instead of relying on tool contracts.
- It handles hooks, safety checks, bounds checking, and Nova Guardrail checks inside the Agent class itself.

### 3. The Empty Controller: `tool_executor.py`
- `ToolExecutionController` was extracted to handle execution but currently just delegates back to `agent._execute_tool_with_safety`. 
- This defeats the purpose of the controller and leaves the safety and dispatch logic tightly coupled to the Agent.

### 4. Unsafe Shell Invocations
- Files like `workspace.py` directly invoke `subprocess.run` (e.g., `git worktree add`, `git add`, `git commit`) without going through any centralized execution or logging policy. This means workspace mutations are invisible to the main tool evidence trail unless manually checkpointed.
- `sandbox.py` is robust but not universally used for all internal executions.

## Action Plan
1. Fully flesh out `ToolDefinition` with `output_schema`, `mutates_workspace`, `requires_network`, and `risk_level`.
2. Ensure every tool returns a typed `ToolResult` containing `status`, `output`, `evidence`, and `error`.
3. Move all tool validation, routing, network-tagging, and hook dispatch out of `agent.py` and into `ToolExecutionController` (or a new `ToolExecutor`).
4. Replace `RAW_TOOL_DEFINITIONS` and `TOOL_DISPATCH` with a centralized `ToolRegistry` that loads `ToolDefinition` objects.
