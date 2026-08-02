# Nexus CLI Reliability & Intelligence Upgrade

## Outcome

This upgrade closes the highest-impact correctness defects reproduced from the supplied audit and hardens the execution path against stale evidence, unsafe fallback, environment contamination, false verification, and persistent-process test drift.

It does **not** make Nexus equal to Claude Code's frontier model intelligence or mature ecosystem. It establishes a substantially more trustworthy base for the next planning, semantic-verification, context-engine, and benchmark phases.

## Implemented fixes

### Run correctness and evidence

- Per-turn evidence now starts from the agent-owned marker; older turns cannot satisfy or poison the current turn.
- Tool retries are reconciled by logical operation plus canonical arguments, not by tool name.
- A successful edit to one file cannot hide a failed edit to another file.
- Re-running the same failed verification command can supersede that exact failed attempt.
- Test metrics now count test evidence only; lint, build, security, and type checks are no longer mislabeled as tests.
- Final reports expose verification-record counts, unique test commands, evidence boundaries, and more useful work descriptions.

### Planning and repository understanding

- Large-repository planning reads the actual repository graph keys and now activates correctly.
- Repository intelligence runs for source archives and non-Git workspaces.
- Complex mutation tasks fail closed when repository understanding fails.
- Planning exceptions fail closed instead of silently degrading to direct execution.
- Step-level criteria are preserved and narrowed rather than overwritten by all plan-level criteria.
- Default hosted-call and token budgets are finite.

### Runtime and process isolation

- Parser/code-validation subprocesses can run in a portable restricted mode without requiring Bubblewrap.
- Shell hooks accept an explicit isolation policy and deny network by default.
- The sandbox backend cache has an explicit reset path for lifecycle and test isolation.
- Remote plaintext custom provider endpoints are rejected; loopback HTTP remains available for local providers.

### Provider reliability

- Provider-key cooldown no longer blocks the interactive thread.
- Cooldown state has one canonical source of truth.
- Provider attempt telemetry records all ordinary SDK exceptions.
- Abandoned or interrupted streams finalize telemetry as cancelled rather than remaining open.
- Repository `.env` files are ignored by the provider runtime and cannot mutate the parent process environment.
- Trusted user-level Nexus environment files are loaded into an isolated mapping.

### Context and tools

- Conversation compaction preserves complete message boundaries, roles, tool-call IDs, and substantially more history.
- Notebook read/edit tools are registered in the capability system and are no longer silently filtered out.

### Qualification and release gates

- Full suite passes in one persistent Python process.
- The release gate now requires both:
  1. one complete persistent-process suite, and
  2. isolated coverage shards.
- Persistent and isolated test counts must agree.
- Real CLI benchmark runs require backend preflight; programmatic harness tests can inject a fake gateway without depending on local credentials.

## Qualification evidence

- `python -m compileall -q nexus tests scripts`: passed.
- Full single-process suite: **496 passed, 2 skipped**.
- Skips are platform-specific macOS and Windows sandbox assertions on the Linux qualification host.
- Wheel build: `nexusai_cli-3.2.1-py3-none-any.whl` built successfully.
- Wheel installation smoke test: passed.
- Installed CLI version check: `NexusAI 3.2.1`.

## Changed source files

- `nexus/agent.py`
- `nexus/api.py`
- `nexus/benchmark.py`
- `nexus/capabilities.py`
- `nexus/cli.py`
- `nexus/code_validation.py`
- `nexus/hooks/runner.py`
- `nexus/memory.py`
- `nexus/pipeline.py`
- `nexus/planner.py`
- `nexus/preflight.py`
- `nexus/repo_graph.py`
- `nexus/run_finalizer.py`
- `nexus/sandbox.py`
- `scripts/run_release_gate.py`
- `tests/test_audit_blockers_fixed.py`

## Integration

### Replace the local source

Extract the supplied full-source archive and use it as the new project directory.

### Apply only the patch

From the root of the older Nexus checkout:

```bash
git apply NEXUS_RELIABILITY_UPGRADE.patch
python -m compileall -q nexus tests scripts
python -m pytest -q
```

### Install the qualified wheel

```bash
python -m pip install --force-reinstall --no-deps nexusai_cli-3.2.1-py3-none-any.whl
nexus --version
```

## Important remaining competitive gaps

The following require additional architecture and product work and are not honestly solved by this patch:

- Model-generated, repository-conditioned candidate plans and strategy comparison.
- First-class uncertainty, assumptions, clarification, and approval objects.
- Criterion-to-symbol-to-test evidence bindings for every requirement.
- Strong semantic completion and hypothesis-driven debugging throughout the main loop.
- One canonical orchestration runtime replacing duplicated managers and kernels.
- Hierarchical semantic context, type/data-flow graphs, runtime traces, and code-aware retrieval.
- Durable multi-agent scheduling, cross-process messaging, event monitors, and richer MCP support.
- Container/VM execution backend and complete Windows execution parity.
- A public 100+ real-repository benchmark with false-success, regression, cost, and intervention metrics.
- IDE, managed CI, updater, marketplace, and enterprise administration surfaces.

## Recommended positioning

Do not claim full Claude Code parity yet. Position this build as a reliability-focused beta of a transparent, affordable, local-first multi-model coding agent, and measure false-success rate before expanding the feature surface.
