# NEXUS CLI and `nova_codex` capability report

Measured on 2026-07-27. The latest local Nova model used by Nexus is the Ollama model named **`nova_codex`**. Nexus exposes it through the model key `nova3b` and aliases including `nova_codex`, `nova`, and `local`.

This report separates model generation ability from Nexus enforcement. “Guarded” means Nexus can detect and stop a bad result; it does not mean `nova_codex` always generates the right result on its first attempt.

## `nova_codex` model

### Proven strengths

- Executes narrow, explicit, single-file create and modify tasks locally.
- Produced independently verified Python entrypoints, Python surgical fixes, C++ programs, and valid JSON manifests in recorded runs.
- Uses the canonical `<<THINKING>>` / `<<FILES>>` protocol with exact file/action metadata when it complies.
- Can repair some protocol, syntax, entrypoint, boundary-condition, and recursive-code failures after receiving concrete verifier output.
- Runs fully locally through Ollama, with no hosted inference charge.

### Nexus-enforced model safeguards

- Exact requested path matching; invented `src/` prefixes and version-like fake paths are rejected.
- Strict `CREATE` versus `MODIFY` semantics; nonexistent modify targets and existing create targets fail.
- Empty, truncated, unbalanced, malformed, and nested-marker output is rejected or canonicalized before application.
- Python AST and JSON parsing; Node syntax checks; Go, C, C++, and Rust compiler checks when the compiler exists.
- Required Python, Go, C/C++, Rust, and JavaScript entrypoint checks.
- Targeted semantic checks for nonnegative boundary errors, recursive self-calls, stable relative-path roots, missing JavaScript built-in imports, and exact-output trailing separators/newlines.
- One clean compiler/semantic repair from the beginning; the hosted two-node path additionally retries Nova and can escalate the individual failed subtask to the Ceiling.
- Candidate files are validated in isolated trees. Failed Nova candidates are never promoted into Ceiling retry context or the real workspace.

### Current limitations

- It is a small local model and remains nondeterministic on exact multi-constraint generation. Repeated runs exposed wrong paths, missing imports, malformed fences, changed boundary behavior, missing entrypoint calls, and subtly wrong relative paths.
- Compiler success is not proof of behavior. Nexus labels completion unverified until a real test/build command or independent behavior assertion passes.
- Complex, ambiguous, multi-file, concurrency, security, database, and architecture tasks should use the two-node mode; Nexus routes known weak spots directly to the Ceiling or escalates after bounded Nova retries.
- It is not honestly equivalent to a frontier hosted coding model. Its practical role is a fast, free Intern behind strict gates.

## Nexus CLI

### Agent and workflow

- Interactive streaming and non-interactive `--print` execution.
- Text, JSON, and stream-JSON outputs with complete local-model/guardrail traces.
- Session autosave, `--continue`, `--resume`, history, compaction, and configurable maximum turns.
- Plans and read-only plan mode; project structure, architecture, active context, and project/user memory.
- Model switching plus visible per-subtask Nova/Ceiling routing reasons, retries, escalations, and free-first counters.

### 22 built-in tools

- Files: read, write, edit, line patch, batch edit, metadata, and diff.
- Search/context: regex code search, glob discovery, directory listing, and compact project tree.
- Shell: blocking commands plus Nexus-owned background start, status/full logs, and stop.
- Git: status, diff, commit, log, and branch operations.
- Web: fetch and search.

### Safety and trust

- Dry-run unified diffs before mutations, with `/apply`, `/reject`, `/edit-pending`, and `acceptEdits` mode.
- Safe, warning, dangerous, and permanently blocked operation classes.
- Dangerous actions require an exact, one-shot confirmation ID; repeating the command does not grant permission.
- Workspace confinement and explicit `--add-dir` authorization; batched edits scope-check every path.
- Content-addressed trust for project instructions, MCP definitions, hooks, and plugin manifests. Any byte change invalidates approval and displays a diff.
- Anti-slopsquatting checks against live PyPI, npm, crates.io, and Go registries before dependency writes or install commands. Missing and unreachable packages are blocked; new/low-download packages warn.
- Web file APIs are workspace-confined and localhost CORS-scoped.

### Verified completion and recovery

- Every applied mutation is re-read, SHA-256 fingerprinted, compiler-checked where applicable, and written to append-only JSONL evidence.
- Commands retain real exit codes and complete raw output; verification paths contain no `|| true` success masking.
- `/verify` re-reads artifact hashes and reruns eligible verification commands, detecting post-completion drift.
- Persistent pre-edit snapshots support `/undo N` and `/rewind N`.
- Compiler/semantic failures roll back real-workspace writes; two-node candidate failures remain isolated.
- Completion prose that claims tests passed without recorded passing evidence is prefixed with `UNVERIFIED TEST CLAIM`.

### Extensibility and interfaces

- Skills, isolated subagents, lifecycle hooks, trust-gated local plugins, and stdio MCP tool discovery/invocation.
- Terminal CLI and Starlette/WebSocket browser UI.
- Project instruction support for `NEXUS.md` and `CLAUDE.md` after explicit digest approval.

## Current Claude Code parity boundary

Nexus now covers the core local coding-agent surface: tool loop, file/shell/git/search tools, diff approvals, permission modes, checkpoints, sessions, project instructions, skills, subagents, hooks, MCP, plugins, background processes, headless output, and evidence-backed verification.

It does not yet implement a long-lived LSP client, automatic per-session Git worktrees, notebook-cell-aware editing, scheduled prompt orchestration, peer-to-peer agent teams, or Anthropic-specific cloud/mobile/IDE/Remote Control services. See `CLAUDE_CODE_PARITY.md` for the source-backed feature comparison.

## Raw verification record

- Deterministic Python suite: **119 passed in 12.68s** on the final run.
- A real eight-scenario matrix achieved 8/8 with native compilers/runtime checks: `verification_evidence/20260727T021905Z/manifest.json`.
- Later repeated matrices are intentionally retained and include 7/8 and 5/8 runs. They demonstrate model nondeterminism and that failures were not relabeled as passes.
- Evidence-complete transcripts and copied JSONL trails are under `verification_evidence/`; each manifest records exact commands, return codes, expected output, actual output, workspace, and per-step verdict.

No benchmark percentage beyond these recorded runs is claimed.
