# Changelog

All notable changes to NexusAI CLI are documented here.

## [Unreleased]

No changes yet.

## [2.0.0] - 2026-07-29

First launch release for the guarded Nexus CLI and Nova 3B v11 integration.

### Added

- Self-contained Nova 3B v11 parser, guardrail, retry, and verification runtime.
- `nexus --doctor` backend and installation diagnostics.
- `nexus --version` and structured success fields for JSON output.
- Deterministic release gate and GitHub Actions test matrix.
- Clean-wheel import and command smoke tests.

### Changed

- Distribution renamed to `nexusai-cli` because `nexusai` on PyPI is unrelated.
- Hosted-provider timeouts default to 60 seconds and remain configurable.
- Groq fallback uses current production model IDs.
- Source and global-checkout launchers are portable across installations.
- Documentation now describes the actual install, approval, and Nova v11 model
  artifact boundary.

### Fixed

- Wheels no longer depend on an adjacent Nova source checkout.
- Framework names such as `Next.js` and `Node.js` are not treated as required
  output file paths.
- Python framework CLIs may use guarded entrypoints such as `cli()` instead of
  a hard-coded `main()` function.
- JavaScript template literals and `Array.join()` no longer trigger false code
  validation failures.
- Hosted Ceiling timeouts work in CLI and background/web worker threads.
- Registry outages produce an explicit approval request instead of being
  misclassified as proof that a package is malicious.
- Out-of-scope paths are confirmed before diff previews or file inspection.
- Relative `desktop/...` paths remain inside the current workspace.
- Groq-only and OpenRouter-only configurations can start hosted mode.
- Non-interactive guardrail and tool failures return a non-zero exit status.
- Web mode binds to loopback, validates browser origins, and does not expose
  common secret-bearing files.

[Unreleased]: https://github.com/akshat92008/nexus_cli/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/akshat92008/nexus_cli/releases/tag/v2.0.0
