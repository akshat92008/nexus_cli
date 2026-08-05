# NEXUS CLI — SANDBOX ISOLATION MODEL

## Overview
`SandboxRunner` (`nexus/sandbox.py`) selects the strongest native OS isolation backend available:
- **Bubblewrap** on Linux
- **`sandbox-exec`** on macOS
- **Restricted Process Fallback** on other environments

## Isolation Classifications
- `STRONG_SANDBOX`: Native kernel-enforced filesystem and network namespace isolation.
- `RESTRICTED_SANDBOX`: Restricted process execution with minimal environment and working directory bounds.
- `POLICY_ONLY`: Fallback execution governed strictly by Python policy checks.
- `UNAVAILABLE` / `BLOCKED`: Returned when `require_os_isolation=True` and no native sandbox backend is present.
