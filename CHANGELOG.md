# Changelog

All notable changes to NexusAI CLI are documented here.

## [Unreleased]

No changes yet.

## [3.0.0] - 2026-07-29

Single integrated Nexus software-engineering runtime.

### Added

- Dependency-aware execution engine with persisted task transitions, focused
  failure classification and repair, verified checkpoints, and independent
  review.
- Automatic Git worktrees for modifying sessions and isolated persistent
  copies for non-Git projects.
- Typed shell-free process execution, native Bubblewrap/macOS sandbox probes,
  filtered environments, limits, visible fallback semantics, and fail-closed
  isolation.
- RepoGraph v2 route, model, configuration, ownership, framework, Git-history,
  and relevance indexing; persistent LSP clients and optional Tree-sitter
  navigation.
- Deterministic API, browser, SQLite, migration-risk, and bounded security
  verification adapters.
- Complete durable lifecycle commands: `runs`, `inspect`, `replay`, `resume`,
  and `rollback`.
- Canonical model/tool/cost logs plus patch, test, checkpoint, and
  `final_report.json` artifacts.
- Structured `.nexus/policies.yml` capabilities and versioned provider, tool,
  and policy extension contracts.
- `nexus run`, CI, local-only, budget, maximum-quality, issue-solving, JSONL,
  and documented cost-control aliases.
- Reproducible `nexus.benchmark.v1` manifests, disposable repository execution,
  typed acceptance checks, scope/cost metrics, and versioned JSON results.
- Nine repository, language-navigation, typed-process, and behavioral tools,
  bringing the built-in tool surface to 34.

### Changed

- Nexus no longer accepts a verified mutation alone as proof that the user
  objective succeeded; deterministic validation and review evidence are
  required for a fully verified result.
- Web sessions use isolated workspaces and modifying CLI modes isolate by
  default.
- Background processes use argv execution and filtered environments instead
  of `shell=True`.
- The run artifact contract now uses the specified `final_report.json` name,
  while readers remain compatible with 2.x reports.

## [2.1.0] - 2026-07-29

Verified-runtime foundation for the long-term Nexus engineering contract.

### Added

- Versioned `nova.patch.v1` JSON protocol support with legacy Nova V11
  compatibility.
- Canonical per-turn run directories containing request, plan, tool events,
  checkpoints, state, costs, acceptance criteria, and final report.
- `/run-status` and `/rollback-run` for durable inspection and complete-run
  rollback.
- Opt-in `--workspace` Git branch/worktree isolation.
- Persistent incremental RepoGraph with Python AST symbols, conservative
  multi-language imports/references, caller lookup, reverse dependencies, and
  impacted-test ranking.
- `repo_index`, `repo_symbols`, and `repo_impact` tools.
- Hard hosted-call, prompt-token, completion-token, and configured-currency
  ceilings.

### Changed

- Plans now persist explicit acceptance criteria, permitted files,
  dependency-aware tasks, risk, retry limits, checks, and tool budgets.
- The hosted Ceiling receives the plan contract and emits the versioned JSON
  patch schema for direct execution.
- Structured CLI results include the final machine-readable run report.
- Repository graph entries refresh incrementally after verified mutations.

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

[Unreleased]: https://github.com/akshat92008/nexus_cli/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/akshat92008/nexus_cli/compare/v2.1.0...v3.0.0
[2.1.0]: https://github.com/akshat92008/nexus_cli/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/akshat92008/nexus_cli/releases/tag/v2.0.0
