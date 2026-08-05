# NEXUS CLI — POLICY ENGINE ARCHITECTURE

## Overview
The `PolicyEngine` (`nexus/security/policy_engine.py`) is the single authoritative security evaluation authority for Nexus CLI. All sensitive operations across tools, process execution, filesystem mutations, network requests, plugins, and subagents pass through the `PolicyEngine`.

## Security Actions
The engine governs 20 typed `SecurityAction` values:
- `READ_FILE`, `WRITE_FILE`, `DELETE_FILE`, `MOVE_FILE`
- `EXECUTE_COMMAND`, `EXECUTE_SHELL`
- `ACCESS_SECRET`, `ACCESS_ENVIRONMENT`
- `OPEN_NETWORK_CONNECTION`, `INSTALL_DEPENDENCY`
- `MODIFY_GIT_HISTORY`, `PUSH_REMOTE`
- `LOAD_PLUGIN`, `START_MCP_SERVER`
- `CREATE_WORKER`, `INCREASE_BUDGET`, `CHANGE_PROVIDER`
- `EXPORT_ARTIFACT`, `ENABLE_TELEMETRY`, `ACCESS_OTHER_WORKSPACE`

## Precedence Hierarchy
Evaluated in strict deterministic order:
1. **Immutable Runtime Safety Rules** (Hard deny for system paths, credential exfiltration, cloud metadata)
2. **Organization Policy** (`OrganizationPolicy`)
3. **Project Policy** (`ProjectPolicy`)
4. **User Policy** (`UserPolicy`)
5. **Run Execution Contract**
6. **One-Time Explicit Approvals**
7. **Safe Defaults**

> [!IMPORTANT]
> Lower precedence policy layers can NEVER weaken a higher layer `DENY`. Unknown or error actions fail closed with `DENY` or `BLOCKED`.
