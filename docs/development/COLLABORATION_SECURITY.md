# COLLABORATION SECURITY AND PRIVACY BOUNDARIES

## Overview
Nexus CLI enforces strict least-privilege security boundaries and prompt-injection defense across all worker agents.

## Security Controls
1. **Least Privilege Scope**: Read and mutation access are restricted per assignment.
2. **Prompt-Injection Resistance**: Repository files may contain malicious instructions (e.g. "ignore scope", "disable tests", "approve patch"). Workers treat repo content as untrusted input; runtime policies always override repository content.
3. **No Direct Peer Messaging**: Workers cannot message each other directly. All coordination routes through `CoordinationBus` and `LeadOrchestrator`.
4. **Credential Protection**: Coordination messages and events automatically scan for and redact credentials (`api_key`, `secret`, `password`, `bearer`).
5. **No Worker Self-Finalization**: Workers cannot issue task-level `VERIFIED` or modify integration checkpoints.
