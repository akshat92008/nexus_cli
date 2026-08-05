# Changelog

All notable changes to NexusAI CLI are documented here.

## [Unreleased]

### Sprint 12 — Independent Benchmarking, Release Qualification, Packaging and Public Launch

- **Independent Benchmark Suite & Runner**: Built `FinalBenchmarkRunner` (`nexus/benchmarks/benchmark_final_runner.py`) and benchmark manifest (`benchmarks/final/manifest.yaml`) executing 12 tasks across 11 task classes (Investigation, Single-file repair, Multi-file repair, Feature implementation, Refactor, Migration, Testing, Debugging/Recovery, Security, Budget, Collaboration, False-Success Prevention) with 100% verified success rate.
- **Zero False-Success Qualification**: Verified fail-closed canonical verification (`tests/test_qualification_sprint12.py`) returning `FAILED` whenever acceptance checks or validators fail, guaranteeing 0 false `VERIFIED` outcomes.
- **Clean-Machine Distribution & Wheel Qualification**: Qualified sdist (`dist/nexusai_cli-3.2.1.tar.gz`) and wheel (`dist/nexusai_cli-3.2.1-py3-none-any.whl`) building (`python3 -m build`), verifying clean venv installation and independent entry point execution (`nexus --version`, `nexus doctor`).
- **Authoritative Release Gate Matrix & Release Tiers**: Established `FINAL_RELEASE_GATES.md` (13/13 mandatory gates passed) and `RELEASE_TIERS.md` qualifying Nexus for `RELEASE_CANDIDATE` and `PUBLIC_BETA` launch tiers.
- **Supply Chain, Dependency & Privacy Governance**: Created `DEPENDENCY_RELEASE_REVIEW.md`, `PRIVACY.md`, `PACKAGING_QUALIFICATION.md`, `DOCUMENTATION_QUALIFICATION.md`, `FINAL_PARITY_SCORECARD.md`, and `LAUNCH_PLAN.md`.
- **Release Manifest & Reproducible Evidence**: Generated `artifacts/release-manifest.json` and `artifacts/sprint-12-final-release.json` documenting exact cryptographic SHA-256 hashes, test summaries (830 passed), security summaries (34 passed), and launch tier recommendations.

### Sprint 11 — Security, Policy Enforcement, Enterprise Controls and Production Hardening

- **Authoritative Security Policy Engine**: Implemented `PolicyEngine` (`nexus/security/policy_engine.py`) with 20 typed `SecurityAction` enums and a 7-tier deterministic precedence hierarchy where org policies and immutable safety rules cannot be weakened by project or user settings.
- **Filesystem Path Security & Protected Paths**: Built `FilesystemSecurity` (`nexus/security/filesystem_security.py`) enforcing canonical path resolution, null byte rejection, traversal blocking, symlink escape detection, workspace containment, and protected credential path guards (`.env`, `.ssh/`, `.aws/`, etc.).
- **Automatic Secret Discovery & Redaction**: Built `SecretScanner` and `SecretRedactor` (`nexus/security/secret_protection.py`) enforcing automatic secret redaction (`[REDACTED]`) across model prompts, tool arguments, outputs, logs, proof receipts, and subagent communication.
- **Command Vector Policy & Execution Hardening**: Built `CommandPolicy` (`nexus/security/command_policy.py`) classifying command risk tiers, denying shell evaluation on untrusted inputs, enforcing array argument vector execution, and blocking dangerous commands (`rm -rf /`, subshell pipes, `chmod 777 /`).
- **Environment Control & Minimal Allowlisting**: Built `EnvironmentControl` (`nexus/security/env_control.py`) constructing minimal allowlisted environments for subprocesses, plugins, workers, and MCP servers.
- **Network Guard & Cloud Metadata/SSRF Defense**: Built `NetworkGuard` (`nexus/security/network_guard.py`) offering 5 network modes (`OFFLINE`, `PROVIDERS_ONLY`, `PACKAGE_REGISTRIES`, `ALLOWLIST`, `UNRESTRICTED_WITH_APPROVAL`) and blocking cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`) and private/loopback IP ranges.
- **Instruction Trust Hierarchy & Prompt Defense**: Built `PromptDefense` (`nexus/security/prompt_defense.py`) enforcing strict instruction trust hierarchy (`SYSTEM_POLICY` > `USER_INSTRUCTION` > `PROJECT_POLICY` > `PLAN_CONTRACT` > `UNTRUSTED_DATA`) and prompt injection scanning.
- **Plugin & MCP Server Security Guard**: Built `PluginMCPGuard` (`nexus/security/plugin_mcp_guard.py`) enforcing manifest validation, permission scope verification, tool-name collision prevention, and command validation for external plugins and MCP servers.
- **Supply Chain Guard**: Built `SupplyChainGuard` (`nexus/security/supply_chain_guard.py`) auditing package manager operations, direct URL/Git dependencies, lifecycle script warnings, and typosquatting risks.
- **Enterprise Policy Engine**: Built `PolicyMerger` (`nexus/security/enterprise_policy.py`) for merging organization and project policy rules without weakening organizational denials.
- **Append-Only Tamper-Evident Audit Logging**: Built `AuditLogger` and `AuditIntegrityVerifier` (`nexus/security/audit_logger.py`) with SHA-256 hash chaining and tamper detection.
- **Security Benchmark & Adversarial Suite**: Built `SecurityBenchmarkRunner` (`nexus/benchmarks/benchmark_security.py`) achieving 12/12 tasks passed, 100% block/allow accuracy, 0 secret leaks, 0 policy bypasses, and 0 sandbox escapes across 34 adversarial and qualification test suites.

### Sprint 10 — Multi-Agent Collaboration, Subagent Coordination and Verified Integration

- **Multi-Agent Collaboration Architecture**: Implemented optional, runtime-governed collaboration system (`nexus/collaboration/`) supporting 6 collaboration modes (`SINGLE_AGENT`, `REVIEW_PAIR`, `SPECIALIST_TEAM`, `PARALLEL_ANALYSIS`, `PARALLEL_IMPLEMENTATION`, `STAGED_COLLABORATION`).
- **Eligibility Engine & Delegation Planner**: Built `CollaborationEligibilityEngine` (`nexus/collaboration/delegation.py`) requiring measurable task benefit before triggering multi-agent execution, defaulting single-symbol or coupled tasks to single-agent execution.
- **Assignment Graph & Cycle Detection**: Built `AssignmentGraph` (`nexus/collaboration/assignments.py`) with cycle detection, topological dependency sorting, and level-grouped execution streams.
- **Workspace Isolation & Scope Reservations**: Implemented `WorkerLifecycleManager` (`nexus/collaboration/lifecycle.py`) managing Git worktrees and temporary workspace copies alongside `ScopeReservationRegistry` (`nexus/collaboration/conflicts.py`) enforcing exclusive mutation bounds.
- **Worker Runtime & Prompt Injection Defense**: Created `WorkerRuntime` (`nexus/collaboration/worker_runtime.py`) protecting worker execution from prompt injection in repository files, returning `LOCALLY_VALIDATED` status without declaring overall task success.
- **Coordination Blackboard & Event Bus**: Built thread-safe `CoordinationBlackboard` and `CoordinationBus` (`nexus/collaboration/coordination.py`) for inter-agent evidence sharing, resource accounting, and audit logging with credential redaction.
- **Independent Result Review Service**: Built `ResultReviewService` (`nexus/collaboration/review.py`) prohibiting worker self-review, checking acceptance evidence, scope bounds, and security findings before issuing `APPROVE_FOR_INTEGRATION`.
- **Patch Integration & Conflict Resolution**: Implemented `IntegrationCoordinator` (`nexus/collaboration/integration.py`) applying patch artifacts to clean integration workspaces with mechanical and semantic conflict checks and SHA-256 tree hash calculation.
- **Independent Central Verification**: Implemented lead orchestrator central verification (`nexus/collaboration/lead_orchestrator.py`) executing verification strictly on the exact integrated tree hash before issuing `COMPLETED`.
- **CLI Commands & Multi-Agent Benchmark**: Added `nexus collaborate` and `nexus collaboration {status|assignments|conflicts|resume|cancel}` subcommands alongside `benchmark_collaboration.py` evaluating multi-agent performance across 4 task classes with 100% selection accuracy and 0% false successes.

### Sprint 9 — Model Doctor, Adaptive Model Routing, Budget Guard and Cost Governance

- **Canonical Model Registry & Descriptors**: Built strongly-typed `ModelDescriptor`, `ModelRegistry`, `PrivacyClass` (`LOCAL_ONLY`, `PRIVATE_INFRASTRUCTURE`, `APPROVED_CLOUD`, `ANY_ALLOWED_PROVIDER`), and `ModelTier` (`LOCAL`, `AFFORDABLE`, `STRONG`, `FRONTIER`) in `nexus/models.py`.
- **Model Doctor Capability Engine**: Implemented `ModelDoctor` (`nexus/model_doctor.py`) executing 6 probe suites across 16 capability dimensions to generate empirical `CapabilityProfile` scorecards and qualitative bands (`STRONG`, `SUITABLE`, `CONDITIONAL`, `WEAK`, `UNSUITABLE`, `UNKNOWN`).
- **Adaptive Model Router**: Created `ModelRouter` (`nexus/model_router.py`) matching task requirements to model capabilities across 6 portfolio modes (`CHEAPEST`, `PRIVATE`, `FASTEST`, `BALANCED`, `STRONGEST`, `MANUAL`) with automated phase downshifting to local/cheap models for low-risk tasks.
- **Evidence-Based Escalation**: Implemented `EscalationController` (`nexus/model_escalation.py`) attributing model failure vs environment/tool failure and restricting provider escalation strictly to capability mismatch evidence.
- **Canonical Cost Accounting Ledger**: Built `CostLedger` (`nexus/cost_accounting.py`) tracking token usage, native USD cost, display INR cost (85 INR/USD), pre-call reservations, and cost per verified task success.
- **Budget Guard Ceilings & Directives**: Enhanced `BudgetController` (`nexus/budget.py`) with `RunBudget`, `--budget-inr` CLI flag support, pre-call reservation checks, and explicit currency budget exhaustion safeguards.
- **Provider Resilience & Privacy Governance**: Built `ProviderResilienceEngine` (`nexus/provider_resilience.py`) normalizing HTTP 429, 401, 404, rate limit retry-after headers, and enforcing local-only privacy policies.
- **CLI Commands & Routing Benchmark**: Added `nexus models`, `nexus model doctor <m>`, `nexus model show <m>`, `nexus model compare <a ><b>`, `nexus budget show`, `nexus cost show` subcommands alongside benchmark `benchmark_model_routing.py` demonstrating a 72% cost reduction vs static ceiling.

### Sprint 8 — Multi-File Engineering, Refactoring, Feature Delivery and Migration Intelligence

- **Canonical EngineeringChangeSet Data Model**: Built strongly-typed `EngineeringChangeSet`, `PlannedFileChange`, `ContractChange`, `ChangeDependency`, `ChangeStage`, `ImpactReport`, and 17 observability events (`nexus/multifile/`).
- **Repository-Scale Impact Analysis**: Implemented `ImpactAnalyzer` querying repository intelligence for direct callers, reverse imports, test coverage, and configuration references with explicit uncertainty surfacing for dynamic references.
- **Topological Change Set DAG**: Built `ChangeDependencyGraph` using Kahn's algorithm for deterministic topological sorting, cycle detection, and parallel-safe grouping.
- **Deterministic Pre-Verification Consistency**: Implemented `ChangeSetConsistencyValidator` enforcing 8 pre-mutation rules (reasons, protected paths, generated files, stale callers, stale imports, schema migrations, package structure, and test changes).
- **Multi-File Patch Manager**: Created `MultiFilePatchManager` with validate-before-apply, unknown/protected file rejection, stale hash protection, and atomic rollback on partial write failures.
- **Bounded Staged Execution & Checkpoints**: Built `StagedChangeSetExecutor` running multi-file changes through bounded stages with checkpoints, intermediate verifier commands, and mandatory gate enforcement.
- **Symbol Rename & Signature Orchestration**: Implemented `SymbolRenameEngine` (safely distinguishing code symbols from strings/docs/configs) and `SignatureChangeOrchestrator` (inventorying callers/implementations and assessing backward compatibility).
- **Migration & Recovery Orchestration**: Implemented `MigrationOrchestrator` (config, schema with approval for destructive edits, dependency upgrades, bounded framework stages) and `MultiFileRecoveryHandler` (missed caller scope expansion up to limit 3, repeated strategy loop prevention).
- **CLI Commands & Benchmark**: Added `nexus change {analyze|validate|execute|status|rollback}` subcommands and `benchmark_multifile.py` achieving < 2ms impact analysis and 8.81ms 50-file patch throughput.

- **Canonical Task & Plan Contracts**: Built typed `TaskContract`, `EngineeringPlan`, `PlanStep`, `AcceptanceCriterion`, and `RequirementSource` provenance models.
- **Ambiguity & Clarification Engine**: Built structured ambiguity detection (`AmbiguityEngine`) distinguishing blocking vs non-blocking questions and suppressing questions answerable from repository intelligence.
- **Independent Plan Critic**: Implemented dedicated `PlanCritic` and `PlanCritique` evaluating initial plans against safety, caller graphs, missing tests, scope bounds, and architecture boundaries with `APPROVE`, `APPROVE_WITH_WARNINGS`, `REVISE`, and `BLOCK` decisions.
- **Deterministic Validation & Graph Analysis**: Implemented `DeterministicValidator` and `PlanDependencyGraph` enforcing step ordering, cycle detection, parallelization safety, and scope bounds.
- **Enforceable Execution Contracts**: Implemented `ExecutionContractGenerator` converting approved plans into runtime-enforceable `ExecutionContract` objects governing allowed tools, mutation scope, budget, and mandatory verification gates before code mutation.
- **Lineage-Preserving Replanner**: Built `PlanReplanner` supporting versioned plan revisions (`v1` -> `v2`) with repeated-signature anti-infinite-loop protection.
- **Planner CLI & Benchmark**: Added `nexus plan "<task>"`, `nexus plan show <run-id>`, and `nexus plan validate <plan-file>` CLI commands alongside dedicated planning benchmark (`benchmark_planning.py`) achieving 100% requirement recall, 100% file recall, and 100% critic defect detection.

### Sprint 5 — Repository Intelligence and Context Engine

- **Canonical Repository Model**: Built strongly-typed `RepositorySnapshot`, `RepositoryFile`, `RepositorySymbol`, `ContextCandidate`, and `ContextBundle` contracts.
- **AST Symbol & Dependency Extraction**: Implemented language-aware AST parsing for Python, JS/TS, Go, Rust, and Java, extracting classes, functions, decorators, routes, ORM models, and re-exports.
- **Explainable Intent Ranking**: Added task-intent classification (`bug_repair`, `feature`, `refactor`, `security`, `config`) with structured ranking rationales and monorepo package isolation.
- **Secret Protection**: Implemented automatic detection and redaction of credentials, private keys, API tokens, and `.env` values before model context presentation.
- **Context Quality Benchmark**: Built dedicated oracle benchmark (`benchmark_context.py`) achieving 100% relevant file recall, 100% test recall, and < 1500 average token cost per query.
- **Consolidation**: Consolidated legacy `ContextManager`, `RepoGraph`, and `ContextSelector` into single authoritative `RepositoryIntelligence` pipeline.

## [3.2.1] - 2026-08-01

Launch-containment and evidence-integrity release.

### Security

- Made the immutable `RunContext` authoritative at tool-execution boundaries,
  including absolute-path and symlink containment.
- Enforced default `ASK` decisions even when no repository policy file exists.
- Removed the macOS sandbox's global host-filesystem read permission and made
  command-capable launch modes require verified native isolation.
- Added pre-spawn rejection for home-directory, credential, traversal, shell
  expansion, interpreter-literal, and absolute host-path access attempts.
- Activated per-agent capability declarations for built-ins, extensions, MCP,
  and isolated plugin tools; undeclared tools are hidden and blocked.
- Required extension filesystem contracts to declare custom read/write argument
  names instead of relying on unsafe path-name heuristics.

### Reliability

- Implemented executable isolated-plugin RPC dispatch instead of advertising
  plugin tools that could only fail as unknown tools.
- Replaced the false-confidence E2E test with a real isolated-worktree workflow
  that reproduces, edits, verifies, independently reviews, and applies only a
  `VERIFIED` result through the normal product path.
- Added baseline-aware verification so unchanged legacy failures are reported as
  inherited while new or modified regressions remain blocking.
- Restricted package-registry checks to newly introduced dependency coordinates,
  preserving existing private dependencies.
- Prevented local Nova validation from being represented as independent semantic
  review; maximum-quality review modes now fail closed without a distinct reviewer.
- Made verified-workspace application atomic and status-sensitive: merge failures
  downgrade the run instead of returning a false success.

### Release qualification

- Added a release-blocking, three-trial live long-horizon benchmark executed in
  verified Bubblewrap isolation, with pass-rate, cost, retry, changed-file,
  external-verification, consistency, and intervention evidence.
- Fixed `generate-dashboard` dispatch and removed the unconditional pytest-timeout
  flag that broke standard test invocation without development extras.
- Consolidated the public SDK contracts onto the runtime extension interfaces and
  added executable SDK compatibility tests.
- Added adversarial containment, plugin RPC, extension capability, baseline
  verification, Nova assurance, CLI, SDK, and full-workflow regression tests.

### Validation

- 340 deterministic tests pass offline.
- Python byte-compilation passes across product, scripts, and tests.
- Wheel build and clean installed-wheel CLI smoke checks pass.
- Live-provider long-horizon qualification remains intentionally release-blocking
  and must pass with configured provider credentials before autonomous claims.

## [3.1.2] - 2026-08-01

Provider-contract and release-qualification hardening.

### Added

- A normalized chat-request contract and machine-readable capability matrix
  for hosted providers and fallback routers.
- Offline provider-chaos coverage for unsupported options, synchronous
  failover, pre-stream failover, and mid-stream replay prevention.
- A configurable concurrent stress matrix that strips provider credentials,
  activates the hosted/web network kill switch, and runs each check from an
  isolated repository copy.

### Fixed

- Hosted provider options are validated before transport and forwarded through
  explicit `NvidiaClient` parameters instead of incompatible arbitrary kwargs.
- The default hosted agent no longer wraps `NvidiaClient`'s built-in failover
  in a redundant one-provider router.
- Fallback routes use their own model ID, retry streams only before the first
  emitted chunk, and expose the capability intersection across routes.
- Benchmark dry-runs now exit nonzero for missing fixtures or blocked tasks,
  and the stale root benchmark manifest points at a shipped fixture.
- No-mutation verification stages report `not_applicable` instead of a
  misleading successful-verification state.
- The release gate uses a writable temporary `uv` cache in restricted CI
  environments and validates every shipped benchmark manifest.
- Hosted inference and both web tools honor `NEXUS_DISABLE_NETWORK` before
  opening a transport; web search now uses DNS pinning and the SSRF policy.
- `requirements.txt` drift from canonical `pyproject.toml` dependencies now
  blocks the release gate.
- Optional prompt, context, MCP, graph, verification, and persistence failures
  in the agent emit structured debug/warning logs instead of being silently
  swallowed.
- Removed the unrelated Pygame Snake application from the production CLI
  repository.

### Validation

- 313 deterministic tests pass offline.
- Ruff, byte-compilation, sdist/wheel build, isolated wheel install, CLI smoke
  checks, benchmark validation, and the concurrent stress matrix pass.

## [3.1.1] - 2026-08-01

Launch-readiness reliability release.

### Fixed

- Direct Nova runs execute model-declared acceptance tests through the normal
  policy sandbox and persist their exit code, raw output, and evidence.
- Pipeline completion is derived from the durable run outcome; partial or
  unverified work can no longer set `PipelineResult.success` to true.
- Nova's generic provider adapter now exposes the common streaming and
  non-streaming response contract instead of accessing a nonexistent field.
- Benchmarks require both Nexus `VERIFIED` status and external checks, count
  local model calls, and preserve internal/external outcomes separately.
- Autonomous dangerous and networked commands fail closed when native OS
  isolation is unavailable.
- Repair attempts require new mutations followed by passing deterministic
  verification; prior mutation evidence cannot make a repair look successful.
- Groq fallback routing no longer selects the scheduled-for-retirement
  `llama-3.3-70b-versatile` model.

### Release engineering

- Removed stale committed wheels, source archives, benchmark claims, and
  historical local run artifacts.
- Added a locked dependency graph, exact wheel-content validation, and a
  tag-release workflow that requires a live provider E2E gate before artifacts
  are published.

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
