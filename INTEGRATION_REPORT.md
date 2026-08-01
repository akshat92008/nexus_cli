# Nexus CLI 3.2.0 Integration Report

## Delivery

- Version: 3.2.0
- Deterministic tests: 340 passed
- Concurrent offline stress: 20 passed, 0 failed
- Byte compilation: passed
- Wheel build: passed
- Installed-wheel smoke: version, doctor diagnostics, dashboard generation, 11-route web app, and packaged static assets verified
- Wheel SHA-256: `510d935e57d07a6f4cc78179ad03e7052bb9d5caed31e0d8ac582e229d2179cf`

## Critical changes

- Authoritative immutable RunContext filesystem confinement.
- Default ASK enforcement and native-sandbox fail-closed policies.
- macOS host-read removal and adversarial command preflight.
- Capability-declared built-in, extension, MCP, and plugin tools.
- Executable isolated-plugin JSON RPC.
- Real verified-worktree E2E application path.
- Baseline-aware verification with stable cross-workspace failure signatures.
- Deterministic-only Nova assurance labeling.
- Newly introduced dependency-only package validation.
- Release-blocking three-trial live long-horizon qualification.
- Canonical SDK compatibility layer and tested dashboard CLI.
- Source-archive provenance fallback for release qualification.

## Changed files

- Added: 4
- Modified: 38
- Removed: 0

### Added

- `LAUNCH_READINESS_3.2.0.md`
- `benchmarks/release_long_horizon.json`
- `tests/test_baseline_verification.py`
- `tests/test_sdk_contract.py`

### Modified

- `.github/workflows/release.yml`
- `CAPABILITIES.md`
- `CHANGELOG.md`
- `CLAUDE_CODE_PARITY.md`
- `README.md`
- `nexus/__init__.py`
- `nexus/agent.py`
- `nexus/capabilities.py`
- `nexus/cli.py`
- `nexus/dashboard.py`
- `nexus/extensions.py`
- `nexus/package_guard.py`
- `nexus/pipeline.py`
- `nexus/plugins/loader.py`
- `nexus/plugins/worker.py`
- `nexus/policy.py`
- `nexus/repair.py`
- `nexus/run_context.py`
- `nexus/sandbox.py`
- `nexus/sdk/__init__.py`
- `nexus/sdk/policy.py`
- `nexus/sdk/tools.py`
- `nexus/tools.py`
- `nexus/verification.py`
- `nexus/workspace.py`
- `pyproject.toml`
- `scripts/run_live_provider_gate.py`
- `scripts/run_release_gate.py`
- `tests/test_cli_coverage.py`
- `tests/test_dashboard.py`
- `tests/test_e2e_full_workflow.py`
- `tests/test_evidence_and_approvals.py`
- `tests/test_extensions_integration.py`
- `tests/test_launch_hardening.py`
- `tests/test_long_horizon_qualification.py`
- `tests/test_plugins_integration.py`
- `tests/test_release_cli.py`
- `uv.lock`

### Removed

- None

## Honest launch boundary

Nexus 3.2.0 is a hardened public-beta launch candidate for verified, reviewable repository engineering. It does not prove unattended Shopify-scale generation or Claude Code model-reasoning parity. The release workflow blocks those claims until repeated live-provider long-horizon trials pass with external verification.
