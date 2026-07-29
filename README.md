# NexusAI CLI

NexusAI is a guarded coding agent for the terminal and browser. A hosted
model can plan and decompose complex work while local Nova 3B v11 executes
well-scoped coding subtasks through Ollama. Every Nova edit must pass
deterministic format, path, constraint, disk-replay, canonicalization, and
compiler checks before it becomes a Nexus tool proposal.

The launch version focuses on a smaller promise that can be verified:

- installed wheels contain the complete Nexus and Nova v11 adapter runtime;
- file changes are scope-checked and presented as diffs before execution;
- dangerous operations require an exact, one-use confirmation;
- dependency changes are checked against real package registries;
- applied changes and verification commands produce persistent evidence;
- failed non-interactive runs return a non-zero process exit code;
- `nexus --doctor` identifies missing local or hosted backends.

Version 2.1 adds the durable runtime required for longer engineering work:

- every request persists a versioned run directory with its request, plan,
  task contract, tool events, checkpoints, acceptance results, costs, and
  final report;
- `--workspace` creates a dedicated Git branch/worktree before Nexus starts;
- persistent repository indexing supports symbol, caller, dependency, and
  impacted-test lookup without sending the entire repository to a model;
- hosted calls, prompt tokens, completion tokens, and configured currency can
  be capped with hard limits;
- hosted direct execution uses the `nova.patch.v1` JSON schema while the local
  Nova V11 adapter remains compatible with its trained Markdown protocol.

See [CAPABILITIES.md](CAPABILITIES.md) for the measured capability boundary,
[ROADMAP.md](ROADMAP.md) for the complete long-term product contract, and
[SECURITY.md](SECURITY.md) for the vulnerability-reporting policy.

## Requirements

- Python 3.10 or newer
- Git for project-aware workflows
- At least one backend:
  - `NVIDIA_API_KEY`, `GROQ_API_KEY`, or `OPENROUTER_API_KEY`; or
  - Ollama with the `nova_codex` Nova 3B v11 model installed

## Install

Install directly from GitHub with `pipx`:

```bash
pipx install git+https://github.com/akshat92008/nexus_cli.git
nexus --version
nexus --doctor
```

Or create an isolated environment from a checkout:

```bash
git clone https://github.com/akshat92008/nexus_cli.git
cd nexus_cli
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/nexus --doctor
```

The distribution name is `nexusai-cli`; the installed command is `nexus`.
The similarly named `nexusai` project on PyPI is unrelated.

## Configure a backend

For hosted planning and execution, export one or more provider keys:

```bash
export NVIDIA_API_KEY="nvapi-your-key"
# Optional production fallbacks:
export GROQ_API_KEY="gsk-your-key"
export OPENROUTER_API_KEY="sk-or-your-key"
```

Nexus also reads `.env` from the current project, the Nexus checkout,
`~/.config/nexus/.env`, or `~/.nexusai/.env`. An existing process environment
value always wins. Avoid passing secrets on the command line.

For local Nova 3B v11, install [Ollama](https://ollama.com), obtain the Nova v11
model artifact from the
[Nova repository](https://github.com/akshat92008/nova-1.5b), and build the
production tag using its v11 Modelfile:

```bash
cd nova-1.5b/legacy/v11
# Place the v11 model artifact named codex_nova beside the Modelfile first.
ollama create nova_codex -f modelfiles/Modelfile.nova_codex
ollama run nova_codex "Create hello.py that prints hello"
```

The model artifact is intentionally not bundled in the Python wheel. Nexus
communicates with it through Ollama and packages the parser, guardrails, retry,
and escalation runtime needed for Nova v11 output.

## Use

```bash
# Interactive hosted mode
nexus

# One prompt with structured automation-friendly output
nexus --print --output-format json "add a health endpoint and tests"

# Local-only Nova v11
nexus --model nova_codex

# Hosted planner with Nova available for atomic subtasks
nexus --model glm-5.2

# Read-only planning
nexus --permission-mode plan "plan the authentication migration"

# Isolated Git branch/worktree for modifying work
nexus --workspace --permission-mode acceptEdits "implement the feature and test it"

# Hard hosted-usage limits
nexus --max-hosted-calls 8 --max-prompt-tokens 100000 \
  --max-completion-tokens 30000 "fix the failing integration tests"

# Browser interface
nexus --web --port 3000
```

Useful startup commands:

```bash
nexus --version
nexus --doctor
nexus --list-models
nexus --help
```

An optional currency ceiling requires explicit prices so Nexus never invents
provider pricing:

```bash
nexus --max-cost-usd 1.00 \
  --input-price-per-million 0.50 \
  --output-price-per-million 1.50 \
  "implement and verify the endpoint"
```

### Approval model

The default permission mode does not apply file edits immediately. Nexus
returns a pending edit with an exact diff:

- `/apply <id>` applies that reviewed proposal;
- `/reject <id>` discards it;
- `/edit-pending <id> <file>` replaces it with reviewed file content;
- `/confirm <id>` executes one exact dangerous or out-of-scope operation;
- `/cancel <id>` discards that operation.

Use `--permission-mode acceptEdits` only in a workspace where automatic edits
are acceptable. Safety blocks and out-of-scope confirmation still apply.

## Models

Hosted model IDs are drawn from the NVIDIA NIM catalog. Provider availability
can change, so `nexus --list-models` is the runtime source of truth.

| Nexus key | Provider model | Role |
|---|---|---|
| `glm-5.2` | `z-ai/glm-5.2` | Default hosted planner |
| `deepseek-v4` | `deepseek-ai/deepseek-v4-pro` | Long-horizon reasoning and coding |
| `deepseek-flash` | `deepseek-ai/deepseek-v4-flash` | Fast coding and tools |
| `kimi` | `moonshotai/kimi-k2.6` | Long-horizon coding |
| `minimax` | `minimaxai/minimax-m3` | Reasoning, coding, and tools |
| `qwen` | `qwen/qwen3.5-397b-a17b` | Software engineering |
| `nemotron` | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | Reasoning and function calling |
| `llama` | `meta/llama-3.3-70b-instruct` | General coding and tools |
| `nova_codex` | Ollama `nova_codex` | Local Nova 3B v11 |

If NVIDIA is unavailable and `GROQ_API_KEY` is configured, Nexus uses Groq
production model IDs only. `openai/gpt-oss-120b` is the default high-capability
fallback, followed by production Llama and GPT-OSS alternatives.

## Verification and evidence

Nexus does not treat an assistant's statement as proof of completion. It
records file mutations, command results, routing decisions, compiler checks,
and package-registry decisions. `/verify` re-reads recent file artifacts and
re-runs safe verification commands; `/verify project` runs detected project
checks.

For contributors, the deterministic release gate is:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python scripts/run_release_gate.py
```

The separate `scripts/run_release_e2e.py` harness makes real model calls and is
therefore an opt-in integration benchmark, not part of offline CI.

## Durable runs and recovery

Every turn is saved under the Nexus state directory with a machine-readable
`request.json`, `plan.json`, `events.jsonl`, checkpoint directory,
`state.json`, and `final-report.json`. Use `/run-status` to inspect the active
run and `/rollback-run` to reverse every applied file operation from that run.
`--continue` and `--resume` restore the associated conversation, plan, and
latest durable checkpoint metadata.

## Built-in tools

Nexus exposes 25 tools across file reading and editing, repository graph
indexing, project search, shell and managed background processes, Git, and web
retrieval. `repo_index`, `repo_symbols`, and `repo_impact` provide persistent
symbol/caller lookup and targeted test-impact analysis. Tool execution is
wrapped by the scope, approval, trust, dependency, budget, run-state, and
evidence layers in `nexus/agent.py`.

Key interactive commands include `/models`, `/project`, `/pending`,
`/permissions`, `/trust`, `/changes`, `/undo`, `/verify`, `/history`,
`/compact`, `/run-status`, `/rollback-run`, and `/help`.

## Development

```bash
.venv/bin/ruff check nexus tests
.venv/bin/pytest
.venv/bin/python -m build
```

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a change.
Release history is in [CHANGELOG.md](CHANGELOG.md). The launch-versus-target
boundary is maintained in [ROADMAP.md](ROADMAP.md).

## License

MIT. See [LICENSE](LICENSE).
