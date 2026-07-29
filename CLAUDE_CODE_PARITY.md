# NEXUS local-agent parity audit

Research date: 2026-07-27. Source of truth: Anthropic's official [Claude Code documentation index](https://code.claude.com/docs/llms.txt), [tools reference](https://code.claude.com/docs/en/tools-reference), [extension overview](https://code.claude.com/docs/en/features-overview), [checkpointing guide](https://code.claude.com/docs/en/checkpointing), and [CLI reference](https://code.claude.com/docs/en/cli-reference).

“Parity” here means local agentic coding capability, not a claim that Nexus can reproduce Anthropic-account services. Cloud hosting, Claude subscriptions, proprietary models, phone push delivery, claude.ai Artifacts, Remote Control, Chrome computer use, Slack/GitHub hosted apps, organization analytics, and Anthropic-managed Routines require external services Nexus does not own. They are explicitly out of scope rather than simulated.

## Implemented and enforced

| Claude Code capability | NEXUS implementation |
|---|---|
| Multi-turn tool loop and streaming | Persistent OpenAI-compatible tool-call loop, streaming terminal UI, bounded turns |
| Read, write, edit, glob/grep, repository graph, shell, git, web | 25 built-in tools in `nexus/tools.py` |
| Diff approval and permission modes | Dry-run unified diff; `/apply`, `/reject`, `/edit-pending`; `default`, `acceptEdits`, and read-only `plan` modes |
| Checkpoint/rewind | Persistent pre-edit snapshots; canonical run checkpoints; `/undo N`, `/rewind N`, `/rollback-run`, `/diff`, `/changes` |
| Session continue/resume | Auto-saved message/tool history, plan restoration, durable run metadata, `--continue`, `--resume`, `/history`, `/resume` |
| Context compaction | `/compact` and automatic compaction on provider context overflow |
| Project instructions/memory | `NEXUS.md`, `CLAUDE.md`, and project decision memory |
| Content trust | Exact SHA-256 approval, diff on every change, immediate deactivation until re-approved |
| Plan/task tracking | Persistent acceptance criteria, permitted paths, dependency-aware tasks, risk, retries, checks, budgets, plan status, read-only plan mode |
| Skills | Built-in and filesystem-loaded skills with automatic activation |
| Subagents | Isolated specialized subagent contexts and templates |
| Hooks | Before/after file, command, commit, test, error, session, and model lifecycle events |
| MCP | Stdio discovery and tool invocation; config is disabled unless its exact bytes are trusted |
| Plugins | Project/global plugins providing skills, hooks, and tools; local manifests are trust-gated |
| Background work | Start, poll, read complete logs, and stop Nexus-owned processes |
| Safety/permissions | Allow/deny tool rules; blocked, dangerous, warning, and safe tiers; exact one-shot dangerous confirmations |
| Large-codebase support | Recursive regex/glob search, compact tree, project/framework detection, persistent incremental symbols/imports/callers/reverse dependencies/impacted tests |
| Non-interactive automation | `-p/--print`, text/JSON/stream-JSON output, `--max-turns`, tool rules, additional authorized directories |
| Model selection | CLI/model command switching plus explicit Ceiling/Nova per-subtask routing reasons |
| Cost visibility and limits | Local/Ceiling counts plus hard hosted-call/token limits; configured-currency limits require explicit prices |
| Verification | Real exit codes and unedited output; no `|| true`; syntax/compile, truncation, entrypoint, literal, path, and disk replay gates |
| Worktree isolation | `--workspace` creates a dedicated Git branch/worktree before the session starts |
| Run reporting | Versioned request, plan, events, checkpoints, costs, criterion outcomes, risks, and final report |

## NEXUS differentiators

1. Verified completion: every actual mutation is re-read, SHA-256 fingerprinted, compiler-checked where applicable, and logged to append-only JSONL. Unsupported test-success prose is flagged.
2. Anti-slopsquatting: dependencies and install commands are checked against PyPI, npm, crates.io, or the Go module proxy before execution.
3. Trust re-verification: changing one byte of project instructions, MCP config, hooks, or plugin metadata invalidates approval.
4. Free-first routing: each subtask records why it stayed local or went directly to the Ceiling, including Nova retries and escalation evidence.

## Honest remaining gaps

| Capability | Status |
|---|---|
| Full LSP symbol navigation | Persistent RepoGraph and compiler diagnostics exist; no long-lived Language Server Protocol client yet |
| Automatic worktree lifecycle | Opt-in branch/worktree isolation exists; Nexus does not yet force it for every modifying run or automatically clean it up |
| Interrupted task continuation | Plans and checkpoints restore, but execution does not automatically restart at the last verified task |
| Notebook cell editing | Files can be edited, but `.ipynb` cell-aware editing is not implemented |
| Scheduled/monitor-triggered prompts | Background processes exist; cron/routine orchestration is not implemented |
| Agent teams with peer messaging | Isolated subagents exist; independent peer-to-peer agent teams are not implemented |
| IDE plugins, voice, mobile, Remote Control, browser computer use | External product surfaces; not simulated |
| Hosted artifacts, PR cloud review, enterprise analytics/policy delivery | Anthropic/cloud services; not simulated |

No row in the remaining-gap table should be described as passing or complete until a real implementation and raw verification transcript exist.
