# Dependency & Supply Chain Release Review — Nexus CLI

This document audits the third-party dependencies, license compatibility, and supply chain security of Nexus CLI `3.2.1`.

---

## 1. Direct Dependencies Audit

| Package | Minimum Version | License | Purpose | Status |
|---|---|---|---|---|
| `openai` | `>=1.30.0` | Apache 2.0 | Hosted LLM API provider gateway | AUDITED |
| `rich` | `>=13.7.0` | MIT | Terminal UI formatting & progress rendering | AUDITED |
| `prompt_toolkit` | `>=3.0.43` | BSD 3-Clause | Interactive REPL & prompt handling | AUDITED |
| `pygments` | `>=2.17.0` | BSD 2-Clause | Syntax highlighting | AUDITED |
| `starlette` | `>=0.37.0` | BSD 3-Clause | Web dashboard ASGI core | AUDITED |
| `uvicorn[standard]` | `>=0.29.0` | BSD 3-Clause | ASGI server runner | AUDITED |
| `websockets` | `>=12.0` | BSD 3-Clause | Real-time event streaming | AUDITED |
| `httpx[socks]` | `>=0.27.0` | BSD 3-Clause | Async HTTP & SOCKS proxy client | AUDITED |

---

## 2. Optional Extras

- `dev`: `build`, `pytest`, `pytest-cov`, `pytest-randomly`, `pytest-timeout`, `ruff`, `setuptools`, `wheel`
- `browser`: `playwright`
- `intelligence`: `tree-sitter-language-pack`

---

## 3. Supply Chain Security Verification

- **Typosquatting & Package Names**: Checked via `nexus.security.supply_chain_guard`. All dependencies match canonical PyPI packages.
- **Direct URL & Git Dependencies**: 0 unverified direct git repository dependencies in release configuration.
- **License Compliance**: All packages use OSI-approved permissive open-source licenses (MIT, Apache 2.0, BSD).

Supply Chain Audit Verdict: **QUALIFIED / ZERO HIGH RISK DEPENDENCY ISSUES**
