# Nexus CLI 3.2.1 — Power & Reliability Upgrade

Source baseline: uploaded `nexus_cli-main (27)(1).zip`

## Executive summary

This patch focuses on real task-completion capability rather than adding more surface features. It strengthens Nexus in the areas that matter most for difficult coding work: persistent recovery, repository-aware context, change-aware verification, transactional editing, dirty-worktree support, secure command execution, provider-independent cloud operation, concurrency safety, and release integrity.

Nova remains optional. The default `--local-intern off` path allows hosted/cloud providers to perform planning and execution without Nova.

This is a material engineering upgrade, but it is not evidence that Nexus has reached Claude Code parity. That claim requires controlled live-provider benchmark runs on real repositories and comparison against the current Claude Code release.

## Major implementation changes

### 1. Persistent execution and recovery

- Added retryable plan steps with preserved failure evidence.
- Added failure fingerprints so repeated unsuccessful strategies are detected.
- Repair prompts now receive repository context, verification evidence, and previous-attempt information.
- Planned hosted execution can re-enter failed steps rather than terminating after the first unsuccessful implementation.
- Increased repair-loop capability while maintaining explicit budgets and termination conditions.

Primary files:
- `nexus/pipeline.py`
- `nexus/planner.py`
- `nexus/repair.py`

### 2. Repository-aware context engine

- Added query-focused context bundles.
- Ranks likely relevant files and symbols.
- Includes focused excerpts instead of indiscriminately loading whole files.
- Includes dependencies, ownership signals, and impacted tests.
- Injects repository context into normal agent and repair prompts.

Primary files:
- `nexus/repo_graph.py`
- `nexus/agent.py`
- `nexus/repair.py`

### 3. Change-aware verification

- Runs impacted tests first when Nexus can identify them.
- Returns focused failure evidence immediately when targeted tests fail.
- Runs the complete deterministic project gate after targeted checks pass.
- Preserves mandatory OS-isolation requirements for verification commands.
- Adds configurable verification timeouts.

Primary files:
- `nexus/verification.py`
- `nexus/agent.py`

### 4. Transactional multi-file editing

- Computes all edited file bodies before committing writes.
- Writes to sibling temporary files and flushes them.
- Uses atomic replacement for commit.
- Rolls back already committed files if a later commit fails.
- Records one coherent history transaction rather than duplicate internal edits.

Primary file:
- `nexus/tools.py`

### 5. Dirty Git repository support

- Nexus no longer rejects a repository merely because it contains user changes.
- Creates an isolated snapshot containing staged, unstaged, and untracked content.
- Separates the user’s pre-existing delta from Nexus-generated changes.
- Applies only Nexus’s delta back to the source repository.
- Refuses apply if the source changed concurrently, preventing silent overwrites.
- Preserves staged/unstaged/untracked state.

Primary file:
- `nexus/workspace.py`

### 6. Unified secure execution boundary

- Added centralized command preparation in `SandboxRunner.prepare()`.
- Foreground commands, background processes, and MCP launch paths now share workspace, environment, and native-sandbox policy.
- Fixed the critical bug where confirming a command removed mandatory OS isolation.
- Blocks inherited credential-like environment variables, including sensitive `NEXUS_*` values.
- Adds explicit, narrow allowlisting for configured MCP secrets.
- Background processes now use unique log names, process groups, timeouts, output limits, cleanup, and synchronized registries.

Primary files:
- `nexus/sandbox.py`
- `nexus/tools.py`
- `nexus/agent.py`
- `nexus/mcp/client.py`

### 7. Web UI session hardening

- Removed the session token from unauthenticated HTML.
- Launches the web UI through a tokenized bootstrap URL.
- Stores the authenticated session in an HttpOnly, SameSite cookie.
- Protects HTTP APIs and WebSockets.
- Adds origin validation, normalized session IDs, stronger token entropy, and locking around session/agent access.

Primary files:
- `nexus/webapp/server.py`
- `nexus/webapp/static/app.js`
- `nexus/cli.py`

### 8. Cloud-only operation retained

- `--local-intern off` remains the default.
- Hosted providers can handle the complete workflow.
- Nova fallback requires explicit enablement.
- No new recovery, context, verification, editing, or workspace feature depends on Nova.

Example:

```bash
export NEXUS_OPENAI_API_KEY='...'
export NEXUS_OPENAI_BASE_URL='https://provider.example/v1'

nexus \
  --model custom \
  --model-id provider/model \
  --local-intern off \
  --working-dir /path/to/repository \
  'Implement the requested feature and verify it end to end'
```

### 9. Concurrency and provider-key safety

- Made round-robin API-key selection and cooldown mutation thread-safe.
- Added synchronization to background-process state.
- Added synchronization to web-session agent creation and per-session execution.

Primary files:
- `nexus/api.py`
- `nexus/tools.py`
- `nexus/webapp/server.py`

### 10. Doctor and release-gate correctness

- Doctor creates/checks the workspace before evaluating sandbox readiness.
- Review mode can diagnose as usable with a hosted provider while clearly warning that command execution remains blocked without native isolation.
- Release gate rejects zero-test/no-collection results.
- Enforces a minimum passing-test count.
- Uses process-isolated test modules to reduce cross-test contamination from subprocess/web/global runtime state.
- Aggregates branch coverage across isolated test processes.
- Generates readiness evidence using the actual package version.

Primary files:
- `nexus/doctor.py`
- `scripts/run_release_gate.py`

## Validation performed

### Source integrity

- `git diff --check`: passed
- `python -m compileall -q -f nexus scripts tests`: passed

### Targeted regression suite

Command group covering new hardening, agent safety, launch regressions, MCP, web auth, workspace behavior, and release gates:

- **44 passed**
- **0 failed**

### Complete test inventory

- **484 tests collected**
- **482 passed**
- **2 skipped** because they are platform-specific sandbox tests
- **0 functional failures** when run in clean grouped processes

The repository’s original single-process full suite can still intermittently stall because tests create global state, subprocesses, sockets, and background workers. The uploaded baseline exhibited this before the patch. The release-gate implementation now isolates test modules at process level and combines coverage, but eliminating every global-state source inside the test architecture remains additional cleanup work.

### Packaging

- Python wheel built successfully.
- Source compilation and installed package structure were validated.

### Benchmark manifests

- Core and long-horizon benchmark manifests pass dry-run validation.
- Dry-run validation confirms manifest structure only; it is not a model capability result.

## Integration instructions

### Option A — replace with the complete source archive

1. Back up your current local repository.
2. Extract the supplied source archive.
3. Copy your private `.env`/credential configuration separately; do not copy generated caches or old virtual environments.
4. Install in editable mode:

```bash
python -m pip install -e .
```

5. Install development/release dependencies before running the full gate:

```bash
python -m pip install pytest coverage pytest-cov ruff build
```

6. Run:

```bash
python scripts/run_release_gate.py
```

### Option B — apply the portable patch

From the root of a clean checkout corresponding to build 27(1):

```bash
git switch -c nexus-power-upgrade
git apply --3way /path/to/Nexus-CLI-3.2.1-Power-Hardening.patch
python -m pip install -e .
python -m pytest -q tests/test_power_hardening.py
```

Review the diff before merging:

```bash
git diff --stat
git diff --check
```

## What this patch does not prove

It does not prove that Nexus equals Claude Code on:

- SWE-bench or other verified coding benchmarks
- very large long-horizon tasks
- current frontier-model reasoning quality
- provider-specific prompt-cache/tool-call optimization
- real-world success rates across many repositories

Those require controlled benchmark runs using the same tasks, repositories, models, budgets, and acceptance tests.

## Recommended next measurement phase

1. Run 30–50 real repository tasks through a selected frontier cloud model with Nova disabled.
2. Compare Nexus and Claude Code using identical commits and acceptance tests.
3. Record completion rate, retries, regressions, cost, elapsed time, and manual intervention.
4. Use failures to improve context ranking, replanning, and provider-specific adapters.
5. Publish only reproducible benchmark claims.

## Files added or substantially upgraded

- `tests/test_power_hardening.py`
- `nexus/agent.py`
- `nexus/api.py`
- `nexus/cli.py`
- `nexus/doctor.py`
- `nexus/mcp/client.py`
- `nexus/pipeline.py`
- `nexus/planner.py`
- `nexus/repair.py`
- `nexus/repo_graph.py`
- `nexus/sandbox.py`
- `nexus/tools.py`
- `nexus/verification.py`
- `nexus/webapp/server.py`
- `nexus/webapp/static/app.js`
- `nexus/workspace.py`
- `scripts/run_release_gate.py`
