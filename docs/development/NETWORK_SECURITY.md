# NEXUS CLI — NETWORK SECURITY ARCHITECTURE

## Overview
`NetworkGuard` (`nexus/security/network_guard.py`) governs all outbound HTTP/HTTPS requests from tools and model providers.

## Operational Modes
- `OFFLINE`: All outbound network connections blocked.
- `PROVIDERS_ONLY`: Connections limited to approved LLM provider endpoints (`api.openai.com`, `api.anthropic.com`, `generativelanguage.googleapis.com`, `openrouter.ai`).
- `PACKAGE_REGISTRIES`: LLM providers plus approved package managers (`pypi.org`, `npmjs.org`, `crates.io`).
- `ALLOWLIST`: Explicit domain allowlist.
- `UNRESTRICTED_WITH_APPROVAL`: Network access requires explicit user confirmation.

## SSRF & Cloud Metadata Defense
Explicitly blocks:
- Cloud metadata endpoints: `169.254.169.254`, `100.100.100.200`, `192.0.0.192`, `metadata.google.internal`, `metadata.azure.com`.
- Private & loopback IP ranges: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`.
- Non-HTTP schemes: `file://`, `ftp://`, `gopher://`, `data:`.
