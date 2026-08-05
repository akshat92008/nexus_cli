# NEXUS CLI — SUPPLY CHAIN SECURITY ARCHITECTURE

`SupplyChainGuard` (`nexus/security/supply_chain_guard.py`) audits dependency operations:
- Audits package manager calls (`npm`, `pip`, `uv`, `cargo`).
- Detects direct URL and Git dependencies, marking them for policy review.
- Flags typosquatting risks against popular packages.
- Controls lifecycle script execution during installation.
