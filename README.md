# NexusAI CLI

NexusAI is an open-source, model-agnostic software-engineering runtime for the
terminal, browser, and headless CI. A hosted model plans and reviews difficult
work; local Nova V11 executes suitable atomic changes through Ollama. Nexus
owns repository understanding, permissions, workspaces, tools, tests, repair,
evidence, budgets, rollback, and recovery.

Version 3.1.1 is the launch-hardening runtime described by the product
specification:

- requests become acceptance criteria and dependency-aware execution
  contracts with risk, file scope, checks, retries, and budgets;
- modifying sessions open an isolated Git worktree, or a persistent temporary
  copy for non-Git projects, unless the user explicitly opts out;
- commands support shell-free argv execution, filtered environments, timeouts,
  output ceilings, native Linux/macOS isolation, and fail-closed isolation;
- persistent RepoGraph indexing covers symbols, imports, callers, tests,
  routes, models, configuration, ownership, frameworks, and Git relevance;
- LSP clients and optional Tree-sitter parsing provide precise navigation;
- Nova V11 and hosted candidates use strict patch contracts, temporary-tree
  replay, compiler checks, bounded repair, escalation, and independent review;
- verification can combine lint, types, tests, build, security, read-only
  database checks, HTTP contracts, and optional browser workflows;
- every run persists request, plan, task, model, tool, cost, patch, test,
  checkpoint, state, and final-report artifacts;
- interrupted work can resume from its latest verified checkpoint;
- SDK contracts, skills, hooks, plugins, subagents, MCP, CI mode, issue
  solving, and a versioned benchmark harness are included.

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

Optional deterministic adapters:

```bash
pip install "nexusai-cli[intelligence]"  # Tree-sitter language pack
pip install "nexusai-cli[browser]"       # Playwright API
playwright install chromium              # Browser executable
```

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
nexus run --prompt "add a health endpoint and tests" --mode autonomous --output json

# Local-only Nova v11
nexus --model nova_codex

# Hosted planner with Nova available for atomic subtasks
nexus --model glm-5.2

# Read-only planning
nexus run --prompt "plan the authentication migration" --mode plan

# Review-only and autonomous execution
nexus run --prompt "implement the feature and test it" --mode review
nexus run --prompt "implement the feature and test it" --mode autonomous

# Hard hosted-usage limits
nexus --max-hosted-calls 8 --max-prompt-tokens 100000 \
  --max-completion-tokens 30000 --max-cost 1.00 \
  "fix the failing integration tests"

# Local, budget, quality, and CI policy presets
nexus run --prompt "add regression tests" --local-only
nexus run --prompt "fix the bug" --prefer-cheap
nexus run --prompt "review authentication" --quality maximum
nexus run --prompt "fix failing checks" --mode ci --output json

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
.venv/bin/pip install -e ".[dev,browser]"
.venv/bin/python scripts/run_release_gate.py
```

The separate `scripts/run_release_e2e.py` harness makes real model calls and is
opt-in for pull requests and mandatory for version-tag release artifacts.

The public benchmark manifest is versioned and shell-free:

```bash
nexus benchmark --manifest benchmarks/core.json --dry-run
nexus benchmark --manifest benchmarks/core.json \
  --output benchmarks/results/nexus-3.1.1.json
```

## Durable runs and recovery

Every turn is saved under the Nexus state directory with `request.json`,
`plan.json`, `tasks.json`, `events.jsonl`, `model_calls.jsonl`,
`tool_calls.jsonl`, `costs.json`, `patches/`, `tests/`, `checkpoints/`,
`state.json`, and `final_report.json`.

```bash
nexus runs
nexus inspect <run-id>
nexus replay <run-id>
nexus resume <run-id>
nexus rollback <run-id>
```

Resume reloads the same workspace, completed task state, and latest verified
checkpoint, then continues only pending or failed work.

## Built-in tools

Nexus exposes 34 built-in tools across file editing, repository intelligence,
LSP/Tree-sitter navigation, shell-free and managed processes, Git, web
retrieval, API checks, browser workflows, database integrity, and bounded
security analysis. Tool execution is wrapped by scope, policy, approval,
trust, package, budget, run-state, and evidence layers.

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
