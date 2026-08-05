# NEXUS CLI — FORMAL THREAT MODEL

## 1. Protected Assets
- **Source Code & Repositories**: Project files, commit history, branch state.
- **Credentials & Secrets**: API tokens, SSH keys, bearer tokens, passwords, `.env` values, cloud credentials.
- **System & Workspace Integrity**: Local filesystem outside workspace, OS execution runtime, system binaries.
- **Model & Provider Configuration**: API endpoints, model router rules, privacy mode, rate limits.
- **Run Evidence & Audit Data**: Step trajectories, proof receipts, audit logs, cost ledgers.
- **Enterprise Governance State**: Roles, permissions, approval history, organization policies.

---

## 2. Trust Boundaries & Interaction Vectors

```
[ User / CLI Interface ] ◄══ (Attributable Commands / Policy) ══► [ Nexus Core Engine ]
                                                                       │
             ┌─────────────────────────┬───────────────────────────────┼──────────────────────────────┐
             ▼                         ▼                               ▼                              ▼
    [ Model Providers ]       [ Tool Execution ]              [ Untrusted Content ]           [ Plugins & MCP ]
   (Cloud / Local Endpoints)  (Sandbox / Subprocess)         (Repo files, READMEs)           (External Servers)
```

1. **User ↔ CLI**: User commands and project policies define the top-level authority.
2. **Nexus Core ↔ Model Provider**: Prompts and completions over TLS; privacy class enforced.
3. **Nexus Core ↔ Tool Execution Engine**: Model output is UNTRUSTED; actions must be validated by `PolicyEngine`.
4. **Nexus Core ↔ Repository Content**: Repo files, READMEs, test fixtures, and comments are UNTRUSTED DATA.
5. **Nexus Core ↔ Plugins & MCP Servers**: External extensions operate in isolated sandboxes with explicit declared permissions.
6. **Nexus Core ↔ Collaboration Workers**: Subagents operate in isolated Git worktrees with strict least-privilege bounds.

---

## 3. Threat Categories & Preventive / Detective Controls

| Threat Category | Threat Description | Attack Vector | Preventive Control | Detective Control | Regression Test |
|---|---|---|---|---|---|
| Unauthorized Path Access | Model or tool reads/writes sensitive files (`.ssh`, `.env`, root) | Path traversal, symlink escape | `PathSecurity` canonicalization & workspace root lock | Audit log `ProtectedPathAccessBlocked` | `test_filesystem_attacks.py` |
| Unsafe Command Execution | Arbitrary command execution or privilege escalation | Shell injection, `shell=True`, subshell chaining | `CommandPolicy` validation, vector execution only | Audit log `CommandExecutionBlocked` | `test_command_attacks.py` |
| Secret Exfiltration | Secrets sent to remote endpoints or persisted in logs/prompts | Tool output capture, error traces, prompt injection | `SecretScanner` & `SecretRedactor` | Redaction filter in event logger | `test_secret_attacks.py` |
| Network Exfiltration / SSRF | Outbound connection to cloud metadata or internal LAN | Unsafe fetch tool, redirect to loopback | `NetworkPolicy` IP/host validation & network modes | Audit log `NetworkRequestBlocked` | `test_network_attacks.py` |
| Indirect Prompt Injection | Repo content overrides system policy or user constraints | Malicious README, code comment, issue text | Instruction Trust Hierarchy beneath model layer | Suspicious instruction detector | `test_prompt_injection.py` |
| Plugin / MCP Abuse | Extension executes unauthorized commands or accesses secrets | Malicious plugin or spoofed tool name | Manifest permission review & sandboxed execution | Sandbox violation logger | `test_plugin_mcp_attacks.py` |
| Supply Chain Attack | Unsafe package installation executing lifecycle scripts | Typosquatted package, direct URL dependency | `PackageGuard` policy & lifecycle script blocking | Dependency audit logger | `test_supply_chain_attacks.py` |
| Policy Precedence Bypass | Project policy attempting to override Org safety policy | `.nexus/policies.yml` in untrusted repo | Deterministic Policy Precedence merger | Policy conflict detector | `test_policy_attacks.py` |
| Audit Tampering | Local modification of audit logs to hide unauthorized actions | Direct file edit of audit JSONL | Cryptographic hash chaining & tamper verification | `AuditIntegrity` verification | `test_audit_attacks.py` |
| Resource Exhaustion / DoS | Infinite loop, memory leak, fork bomb, huge output generation | Malicious code loop or large file generation | Wall-clock timeouts, memory limits, output caps | Resource monitor | `test_resource_attacks.py` |

---

## 4. Residual Risks & Environmental Scope
- Local root/admin users retain full OS authority to modify files on disk directly outside Nexus runtime controls.
- Cloud model provider server-side data retention policies are governed by third-party provider agreements.
