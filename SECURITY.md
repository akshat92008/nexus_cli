# Security Policy — Nexus CLI

## Supported Versions
Security fixes are applied to the latest release line. Pre-release branches and historical checkouts receive continuous security hardening.

## Core Security Invariants
1. **Model Output is Untrusted**: Models cannot authorize their own actions or relax security policy beneath the model layer.
2. **Repository Content is Untrusted**: README instructions, source comments, and issue text cannot override system policy or user authority.
3. **Least Privilege & Deny-by-Default**: Unknown security actions, path traversals, or unapproved network requests fail closed with `DENY` or `BLOCKED`.
4. **Deterministic Precedence**: Immutable Runtime Rules > Organization Policy > Project Policy > User Policy > Run Contract > Approval > Default.
5. **Secret Redaction**: API keys, bearer tokens, SSH keys, and cloud credentials are automatically redacted across model context, terminal output, and log events.
6. **Tamper-Evident Audit Logging**: Append-only security event logs use SHA-256 hash chaining.

## Report a Vulnerability
Do not open a public issue for a suspected vulnerability. Use GitHub's **Security** tab and choose **Report a vulnerability** to send a private advisory to the maintainers. Include a minimal reproduction using synthetic credentials.
