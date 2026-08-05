# Final Release Gate Matrix — Nexus CLI

This document contains the authoritative release gate matrix for Nexus CLI Sprint 12.

---

## Release Gate Matrix

| Gate ID | Category | Requirement | Release Tiers Affected | Verification Method | Status | Waiver |
|---|---|---|---|---|---|---|
| `GATE-INT-01` | Integrity | Zero false `VERIFIED` outcomes across false-success suite | ALL TIERS | `test_no_fake_success_markers.py`, `test_qualification_sprint12.py` | PASS | FORBIDDEN |
| `GATE-INT-02` | Integrity | Final verified tree equals final workspace tree | ALL TIERS | Baseline verifier checksum evaluation | PASS | FORBIDDEN |
| `GATE-EXE-01` | Execution | All process spawns governed by `ProcessGateway` | ALL TIERS | Security adversarial test suite | PASS | FORBIDDEN |
| `GATE-EXE-02` | Execution | Execution timeouts and process cancellation clean child processes | ALL TIERS | Process tree audit & teardown tests | PASS | FORBIDDEN |
| `GATE-REP-01` | Repo Intel | Context selection prioritizes task-relevant files and symbols | BETA / STABLE | `test_repository_intelligence.py` | PASS | ALLOWED (Alpha) |
| `GATE-PLN-01` | Planning | Engineering plans contain explicit, independently verifiable criteria | BETA / STABLE | `PlanCritic` validation suite | PASS | FORBIDDEN |
| `GATE-REC-01` | Recovery | Failed strategies trigger strategy change or honest termination | ALL TIERS | `test_recovery_intelligence.py` | PASS | FORBIDDEN |
| `GATE-MUL-01` | Multi-File | Cross-file changes evaluate caller impact and preserve contracts | BETA / STABLE | `test_multifile_contracts.py` | PASS | ALLOWED (Alpha) |
| `GATE-CST-01` | Cost | Hard budget enforcement prevents un-authorized token spend | ALL TIERS | `test_qualification_sprint9.py` | PASS | FORBIDDEN |
| `GATE-COL-01` | Collaboration | Worker agents run in isolated workspaces with central lead verifier | BETA / STABLE | `test_collaboration_integrity.py` | PASS | ALLOWED (Alpha) |
| `GATE-SEC-01` | Security | Zero secret leakage, path traversal, or shell injection | ALL TIERS | `test_security_adversarial.py` | PASS | FORBIDDEN |
| `GATE-PKG-01` | Packaging | Clean installation of wheel/sdist in isolated venv without repo source | ALL TIERS | `test_e2e_installed_wheel.py` | PASS | FORBIDDEN |
| `GATE-DOC-01` | Docs | All CLI subcommands in README pass automated validation | ALL TIERS | Documentation qualification test | PASS | FORBIDDEN |

---

## Gate Execution Summary

All mandatory gates for `PUBLIC_BETA` and `RELEASE_CANDIDATE` have passed validation.
