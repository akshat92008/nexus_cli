# Nexus CLI product contract and roadmap

Updated: 2026-07-29

## North star

Nexus CLI is an open-source, model-agnostic software-engineering runtime that
turns natural-language goals into tested, reviewable changes.

The long-term product promise is:

> Give Nexus a goal. Nexus understands the repository, creates a plan,
> implements the change, verifies the result, repairs failures, and returns a
> reviewable working diff.

Nexus is the product. Nova V11 is one low-cost local execution worker within
the product. Hosted models may plan, review, or handle difficult subtasks, but
no model is the source of truth.

## Non-negotiable engineering principles

1. **Models propose; Nexus verifies.** The repository, compiler, tests, static
   analysis, and runtime evidence determine success.
2. **No success without evidence.** Generated code alone is never a verified
   result.
3. **Use the cheapest capable model.** Deterministic tools and local models
   handle bounded work; stronger models handle architecture and escalation.
4. **Persist important state.** Requests, plans, patches, commands, evidence,
   costs, failures, approvals, and checkpoints must survive process restarts.
5. **Work inside controlled boundaries.** Filesystem, command, network,
   package, Git, database, and deployment authority must be explicit.
6. **Make uncertainty visible.** Results must be labelled `VERIFIED`,
   `PARTIALLY VERIFIED`, `UNVERIFIED`, `BLOCKED`, `FAILED`, or
   `AWAITING APPROVAL`.

## Capability labels

- **Implemented** means the launch package contains the behavior and the
  deterministic suite exercises its critical path.
- **Partial** means an early implementation exists but does not yet satisfy the
  complete product contract.
- **Planned** means the capability is part of the long-term design and must not
  be advertised as available.

## Version 2.1 implementation boundary

| Area | Status | Version 2.1 evidence boundary |
|---|---|---|
| Installable CLI | Implemented | Self-contained wheel, `nexus` entry point, version and doctor smoke checks |
| Hosted + local model routing | Implemented | Hosted planner paths plus local Ollama `nova_codex` executor |
| Nova V11 task contract | Implemented | Bounded tasks, canonical parser, path and action checks |
| Candidate isolation | Implemented | Nova output is replayed and validated in temporary candidate directories |
| Workspace isolation | Partial | Path confinement plus opt-in `--workspace` branch/worktree isolation; making isolation automatic for every modifying run remains planned |
| File approvals | Implemented | Exact diff preview, apply, reject, replacement, and one-use confirmations |
| Command safety | Partial | Typed Nexus tools, classifications, approvals, timeouts, and output capture; OS/container sandboxing remains planned |
| Package safety | Implemented | Registry checks; missing packages block; registry outages require explicit approval |
| Syntax and compiler checks | Implemented | Python, JSON, Node, Go, C, C++, and Rust where local compilers exist |
| Behavioral verification | Partial | Project test/build discovery and evidence exist; browser/API/database verification remains planned |
| Evidence trail | Implemented | Persistent JSONL records, hashes, command exit codes, and re-verification |
| Recovery | Partial | Canonical run state, verified checkpoints, complete-run rollback, conversation resume, and plan restoration exist; automatic continuation from an interrupted task remains planned |
| Repository intelligence | Partial | Persistent incremental RepoGraph, Python AST symbols, multi-language imports/references, callers, reverse dependencies, and impacted tests exist; Tree-sitter and long-lived LSP mapping remain planned |
| Extensions | Partial | Skills, hooks, plugins, subagents, and stdio MCP exist; stable public SDKs and registry remain planned |
| Headless operation | Implemented | Print, JSON, stream-JSON, meaningful process status, and CI-compatible diagnostics |
| Web interface | Implemented | Loopback-only Starlette/WebSocket UI with workspace and sensitive-file controls |
| Cost controls | Implemented | Hard hosted-call, prompt-token, completion-token, and configured-currency ceilings plus persisted usage reports |
| Run contract and final report | Implemented | Versioned request, plan, event, checkpoint, state, acceptance-result, cost, risk, and final-report artifacts |
| Public benchmarks | Partial | Reproducible local evidence harness exists; versioned public benchmark program remains planned |

## Phase 1 — Reliable core

Objective: make small and medium repository changes safely and consistently.

Version 2.0 delivered the launch foundation, and version 2.1 adds the durable
runtime, worktree mode, hard usage limits, and persistent repository graph:

- clean package installation;
- a packaged Nova V11 adapter instead of a neighboring-checkout dependency;
- safe path handling and workspace confinement;
- guarded tool execution and exact approvals;
- candidate replay and compiler validation;
- evidence-backed mutations and commands;
- CI, build, and isolated-wheel smoke tests;
- provider diagnostics and machine-readable exit behavior.

Remaining Phase 1 exit criteria:

- make the versioned `nova.patch.v1` JSON schema the local Nova default after
  retraining or compatibility validation, then retire the legacy parser;
- make isolated Git worktrees automatic for every modifying run rather than an
  opt-in operating mode;
- add an OS/container sandbox with enforceable network and environment policy;
- resume an interrupted run from its most recent verified checkpoint;
- add platform-specific release tests for Linux, macOS, and Windows.

## Phase 2 — Verified agent

Objective: complete well-defined features and bug fixes with measurable
evidence.

Required capabilities:

- translate requests into explicit acceptance criteria;
- create dependency-aware task DAGs;
- attach permitted files, budgets, checks, retry policy, and risk to every task;
- discover targeted validation commands from project metadata and CI;
- classify failures and generate minimal repairs;
- rerun the smallest relevant validation after each repair;
- escalate after a bounded retry ceiling;
- use an independent reviewer for correctness, scope, architecture, tests, and
  security;
- enforce per-run token and currency ceilings;
- report every satisfied, skipped, blocked, and unverified criterion.

Version 2.1 foundations now persist acceptance criteria, permitted files,
dependency-aware task metadata, risk, retry ceilings, tool budgets, hosted
usage ceilings, checkpoints, and final criterion outcomes. The remaining Phase
2 work is to make this contract drive every task transition and repair loop,
then validate it on a meaningful held-out feature/bug-fix suite.

Phase 2 is complete only when Nexus can reproducibly solve a meaningful suite
of feature and bug-fix tasks without false success.

## Phase 3 — Repository intelligence

Objective: understand large repositories without sending the entire codebase
to a model.

Required capabilities:

- persistent RepoGraph connecting files, symbols, references, imports, tests,
  routes, database models, configuration, ownership, and Git changes;
- Tree-sitter and native AST indexing;
- long-lived Language Server Protocol clients where appropriate;
- symbol and caller lookup;
- dependency and test-impact graphs;
- Git-aware relevance ranking;
- task-local context selection, deduplication, caching, and bounded logs;
- incremental index updates after every accepted patch.

## Phase 4 — One-prompt engineering workflows

Objective: implement complex features and applications milestone by milestone.

Required capabilities:

- clarify only high-value unknowns and propose safe defaults;
- turn broad goals into a product specification and architecture;
- scaffold and implement backend, frontend, database, authentication,
  integrations, and tests incrementally;
- launch and inspect services;
- validate APIs, database mutations, browser behavior, console errors,
  accessibility, and responsive states;
- detect destructive migrations and require elevated approval;
- perform security checks without overstating audit coverage;
- prepare deployment configuration and documentation;
- return a working diff plus evidence and remaining risks.

This phase does not mean one model generates an application in one response.
Nexus manages a checkpointed software-development lifecycle across models and
deterministic tools.

## Phase 5 — Platform ecosystem

Objective: make Nexus an extensible engineering platform.

Required capabilities:

- stable provider, tool, policy, skill, hook, and plugin SDKs;
- versioned MCP integration;
- issue-to-pull-request workflows;
- IDE and CI integrations;
- headless policy profiles;
- extension signing, trust, compatibility, and discovery;
- public benchmark datasets, harnesses, results, and regression dashboards.

## Long-term operating modes

- **Plan:** inspect, search, estimate, and plan without modifying files.
- **Review:** propose patches and commands, then wait for approval.
- **Workspace:** edit and verify inside an isolated Git worktree.
- **Autonomous:** execute only pre-approved policies and stop at protected
  actions.
- **Local-only:** use Nova V11 or another local model with cloud providers
  disabled.
- **Maximum quality:** use stronger planning and review models plus broader
  verification.
- **Budget:** prefer deterministic tools and low-cost models, escalating only
  when necessary.

## Final report contract

Every completed run should report:

- objective and acceptance criteria;
- work completed and files changed;
- tests and checks executed with real outcomes;
- checks skipped or unavailable;
- dependencies added;
- permissions, network calls, and model providers used;
- token and monetary cost;
- assumptions and remaining risks;
- one evidence-based verification status.

The system must never convert missing credentials, unavailable services,
registry outages, or skipped checks into a false success.

## Reliability and benchmark targets

Nexus will optimize for:

- verified task-completion rate;
- regression-free completion rate;
- false-success rate;
- cost per verified task;
- unnecessary file-touch rate;
- successful resume rate;
- command failure rate;
- human intervention rate;
- average repair attempts;
- consistency across repeated runs.

The primary KPI is:

> How often does Nexus declare success when every acceptance criterion is
> genuinely satisfied?

The false-success rate should approach zero. Public capability claims must be
tied to a Nexus version and reproducible evidence.

## End-state flow

```text
Simple user request
        ↓
Deep repository understanding
        ↓
Structured engineering plan
        ↓
Cost-efficient model orchestration
        ↓
Safe code execution
        ↓
Automatic testing and repair
        ↓
Verified working result
```

This roadmap is a delivery contract, not a claim that every target capability
already exists. Current measured behavior remains documented in
[CAPABILITIES.md](CAPABILITIES.md).
