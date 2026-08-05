# NEXUS CLI — SECRET DISCOVERY & REDACTION ARCHITECTURE

## Overview
`SecretScanner` and `SecretRedactor` (`nexus/security/secret_protection.py`) scan and redact credentials from terminal outputs, model prompts, tool results, logs, events, proof receipts, and collaboration subagent messages.

## Detected Secret Types
- OpenAI / Anthropic API Keys (`sk-...`, `sk-ant-api...`)
- AWS Access Keys & Secrets (`AKIA...`)
- GitHub / GitLab / Slack Tokens (`ghp_...`, `xoxb-...`)
- Private Keys (`-----BEGIN RSA PRIVATE KEY-----`)
- HTTP Bearer Tokens (`Bearer ...`)
- Database Connection Strings (`postgres://...`, `redis://...`)

## Redaction Strategy
All matching tokens are replaced with `[REDACTED]` in-memory before serialization or network transmission.
