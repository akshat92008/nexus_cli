<h1 align="center">
  ⚡ NexusAI v2.0
</h1>

<p align="center">
  <strong>A guarded two-node AI coding agent — CLI + Web Interface</strong><br>
  <em>22 Tools • Verified Completion • Registry Guard • Content-Addressed Trust • Nova-First Routing</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/NVIDIA-API%20Catalog-76B900?style=for-the-badge&logo=nvidia" />
  <img src="https://img.shields.io/badge/Tools-22-blue?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Routing-Free--First-green?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Python-3.10+-yellow?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/Interface-CLI%20%2B%20Web-purple?style=for-the-badge" />
</p>

---

## 🚀 What is NexusAI?

NexusAI is a two-node coding agent: a hosted NVIDIA API model acts as the **Ceiling** planner/decomposer, while local **Nova 3B v11** acts as the fast Intern for simple atomic subtasks. It has **22 built-in tools**, full **git integration**, **web search**, **persistent checkpoints**, **conversation memory**, and both a **terminal CLI** and a web interface.

The Ceiling model plans and handles complex or ambiguous work. Nova 3B handles well-specified subtasks fast and free, locally. A guardrail layer automatically catches and either corrects or escalates Nova's known failure modes. Nova is not presented as equivalent in reliability to the Ceiling model.

See [CAPABILITIES.md](CAPABILITIES.md) for the measured `nova_codex` and Nexus CLI capability map, and [CLAUDE_CODE_PARITY.md](CLAUDE_CODE_PARITY.md) for the source-backed parity boundary.

### The verifiable, honest, free-first coding agent

Nexus does not accept an agent's sentence as proof that work succeeded. It records an append-only JSONL evidence trail for file mutations, commands, routing, compiler checks, and package-registry checks. File changes are re-read and hashed after applying; tests are represented by their real command, exit code, and unedited output. `/verify` re-reads recent file artifacts and re-runs safe verification commands.

Before a dependency is written or installed, Nexus queries its real PyPI, npm, crates.io, or Go registry endpoint. Missing or unreachable packages are blocked; unusually new or low-download packages are surfaced as warnings. Project instructions, MCP definitions, and plugin manifests are trusted by exact SHA-256: any byte change disables their use until the new diff is explicitly approved.

### Why NexusAI?

- 🔎 **Verified completion** — persistent evidence instead of self-reported success
- 🧯 **Anti-slopsquatting** — real registry checks before dependency changes
- 🔐 **Trust re-verification** — config approval is invalidated on every content change
- 🆓 **Free-first routing** — atomic tasks stay on local Nova when its guarded capability is sufficient
- 🛠️ **22 powerful tools** — files, git, shell, background process control, web search, multi-edit
- 🧠 **Smart context** — auto-reads project structure, git status, config files
- ↩️ **Checkpoint system** — every file change is tracked; `/undo N` rewinds multiple operations
- 💾 **Memory** — conversations persist across sessions
- 🌐 **Two interfaces** — terminal CLI + premium web UI
- 🤖 **Ceiling + Intern architecture** — the Ceiling model plans and handles complex or ambiguous work; Nova 3B handles well-specified subtasks fast and free, locally
- 🛡️ **Guarded Nova execution** — path validation, constraint verification, disk-safe patching, one retry, then per-subtask escalation to the Ceiling model

## ⚡ Quick Start

### 1. Get Your Free API Key

1. Go to [build.nvidia.com](https://build.nvidia.com)
2. Create a free account (no credit card needed)
3. Generate an API key (starts with `nvapi-`)

### 2. Install & Run

```bash
cd coding_agent

# Install dependencies
pip install -r requirements.txt

# Set your API key
export NVIDIA_API_KEY="nvapi-your-key-here"

# Terminal CLI
python run.py

# Hosted Ceiling + local Nova 3B v11 Intern
python run.py --model kimi "add a health endpoint and tests"

# Local-only Nova 3B v11 path (requires Ollama)
python run.py --model nova_codex

# Web Interface (Cursor-like UI)
python run.py --web

# Web Interface on custom port
python run.py --web --port 8080
```

Install the durable global command (recommended on this Mac; it avoids modifying
the externally-managed Homebrew Python):
```bash
bash scripts/install_nexus_command.sh

# CLI mode
nexus

# Web mode
nexus --web
```

Nexus automatically loads `NVIDIA_API_KEY` (and optional fallback keys) from
`coding_agent/.env`; do not paste keys into commands. From any directory,
`nexus` runs this checkout. Use `nexus --model nova_codex` for local-only Nova,
or `nexus --model glm-5.2` / `nexus --model kimi` for a hosted Ceiling model.

### 3. One-Line Launcher
```bash
bash nexus.sh           # CLI mode (auto-installs deps)
bash nexus.sh --web     # Web mode
```

## 🛠️ 22 Agent Tools

| Category | Tool | Description |
|----------|------|-------------|
| **File** | `read_file` | Read file contents with line numbers |
| **File** | `write_file` | Create/overwrite files (tracked for undo) |
| **File** | `edit_file` | Surgical find-and-replace edits (tracked) |
| **File** | `patch_file` | Line-range based editing (tracked) |
| **File** | `multi_edit` | Batch edits across multiple files (tracked) |
| **File** | `file_info` | File metadata (size, perms, lines, MD5) |
| **File** | `diff_files` | Unified diff between two files |
| **Search** | `search_code` | Regex search across codebase |
| **Search** | `list_directory` | List directory contents |
| **Search** | `find_files` | Find files by glob pattern |
| **Search** | `get_project_structure` | Project tree view |
| **Shell** | `run_command` | Execute shell commands (blocking) |
| **Shell** | `process_run` | Start background processes |
| **Shell** | `process_status` | Poll a Nexus-managed process and read complete logs |
| **Shell** | `process_stop` | Stop only a process previously started by Nexus |
| **Git** | `git_status` | Full repository status |
| **Git** | `git_diff` | View diffs (working/staged/commits) |
| **Git** | `git_commit` | Stage and commit changes |
| **Git** | `git_log` | View commit history |
| **Git** | `git_branch` | List/create/switch/delete branches |
| **Web** | `web_fetch` | Fetch and read any URL |
| **Web** | `web_search` | Search the web (DuckDuckGo) |

## ⌘ CLI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/models` | List all available models |
| `/model <name>` | Switch the Ceiling model (e.g., `/model kimi`) or use local-only Nova (`/model nova_codex`) |
| `/confirm <id>` | Explicitly execute the exact dangerous operation Nexus previously held pending |
| `/cancel <id>` | Cancel a pending dangerous operation without executing it |
| `/pending` | List file diffs waiting for approval |
| `/apply <id>` | Apply one exact reviewed diff |
| `/reject <id>` | Reject a diff without touching disk |
| `/edit-pending <id> <file>` | Replace a pending proposal with reviewed file content |
| `/tools` | List all 22 agent tools |
| `/git` | Show git status |
| `/undo [N]` | Undo the last N file operations |
| `/rewind [N]` | Rewind tracked code state |
| `/diff` | Show the last change as a diff |
| `/changes` | List all file changes this session |
| `/history` | List saved conversations |
| `/resume <id>` | Resume a previous conversation |
| `/compact` | Compress conversation to save context |
| `/clear` | Clear conversation history |
| `/reset` | Reset session and clear screen |
| `/project` | Show project structure |
| `/cost` | Show token usage stats |
| `/verify [N]` | Re-check recent evidence and re-run verification commands |
| `/verify project` | Run detected project lint, type, test, and build commands |
| `/permissions <mode>` | Switch between `default`, `acceptEdits`, and read-only `plan` |
| `/trust [approve\|reject] <path>` | Approve or reject the exact current config digest |
| `/init` | Create a starter `NEXUS.md` project guide |
| `/context` | Show architecture and active-context summaries |
| `/system <prompt>` | Set custom system prompt |
| `/save <file>` | Save conversation to JSON |
| `/multi` | Multi-line input mode |
| `/exit` | Exit NexusAI |

## 🌐 Web Interface

Launch with `nexus --web` for a premium, Cursor-like experience:

- **Dark mode glassmorphism design** — frosted glass panels, smooth gradients
- **Real-time streaming** — responses appear token-by-token via WebSocket
- **Tool call visualization** — expandable cards showing every tool call and result
- **File tree sidebar** — browse your project directly in the UI
- **Model selector** — switch hosted Ceiling models or choose local-only Nova 3B v11
- **Code syntax highlighting** — with copy buttons and language labels
- **Responsive design** — works on desktop and mobile
- **Keyboard shortcuts** — Enter to send, Shift+Enter for new line

## 📦 Available Models

| Model | Category | Context | Best For |
|-------|----------|---------|----------|
| **DeepSeek V4 Pro** | Reasoning | 131K | Complex reasoning & coding |
| **DeepSeek R1** | Reasoning | 131K | Chain-of-thought reasoning |
| **GLM 5.2** | Reasoning | 131K | Agentic tasks & reasoning |
| **Kimi K2.6** | Coding | 131K | Long-horizon coding & tool use |
| **Nova 3B v11** | Local Intern | 32K | Handles simple, well-specified subtasks locally; guardrails validate every edit, retry once, or escalate failures instead of applying them silently |
| **Nemotron Ultra 550B** | Reasoning | 131K | NVIDIA's flagship model |
| **Nemotron 70B** | General | 131K | Fast all-rounder |
| **Qwen 2.5 72B** | General | 131K | Strong code & math |
| **Qwen Coder 32B** | Coding | 64K | Specialized coding |
| **Llama 3.1 405B** | General | 131K | Meta's largest model |
| **Llama 3.1 70B** | General | 131K | Fast & capable |
| **Mixtral 8x22B** | General | 64K | MoE speed |
| **Mistral Large 2** | Reasoning | 131K | Mistral's flagship |
| **Gemma 2 27B** | General | 8K | Efficient & fast |

## 🏗️ Architecture

```
coding_agent/
├── nexus/
│   ├── __init__.py              # Package init
│   ├── cli.py                   # CLI entry point & REPL
│   ├── agent.py                 # Core agent: two-node routing, safety, auto-save
│   ├── two_node_backend.py      # Ceiling decomposition + Nova Intern execution
│   ├── api.py                   # NVIDIA API client (OpenAI-compatible)
│   ├── models.py                # Model registry & aliases
│   ├── tools.py                 # 22 tools: file, git, shell, web, search
│   ├── evidence.py              # Append-only completion evidence and re-verification
│   ├── package_guard.py         # PyPI/npm/crates.io/Go registry validation
│   ├── trust.py                 # Content-addressed config approval
│   ├── approvals.py             # Non-mutating diff previews and pending edits
│   ├── code_validation.py       # Syntax, compiler, entrypoint, truncation gates
│   ├── ui.py                    # Rich terminal UI & formatting
│   ├── history.py               # Undo/diff file change tracking
│   ├── memory.py                # Conversation persistence & compaction
│   └── webapp/                  # Web interface
│       ├── __init__.py
│       ├── server.py            # Starlette + WebSocket server
│       └── static/
│           ├── index.html       # Premium dark-mode chat UI
│           ├── styles.css       # Glassmorphism + animations
│           └── app.js           # WebSocket streaming + file tree
├── run.py                       # Quick launcher
├── nexus.sh                     # Auto-setup bash launcher
├── pyproject.toml               # Package config (v2.0.0)
├── requirements.txt             # Dependencies
└── README.md                    # This file
```

## 💡 Tips

- **Model aliases work:** `/model ds` instead of `/model deepseek-v4`
- **Two-node default for coding:** hosted models plan and decompose; Nova 3B v11 executes simple atomic subtasks; guardrails catch and either fix or escalate Nova mistakes
- **Local Nova option:** `/model nova_codex` uses the latest v11 model directly. It is fast and free, but not equivalent to the hosted Ceiling models.
- **Auto-context:** The agent reads your project structure and git status on the first message
- **Undo everything:** Every file change is tracked — use `/undo` to revert, `/diff` to review
- **Resume conversations:** `/history` to list, `/resume <id>` to continue
- **Compact long chats:** Use `/compact` when the conversation gets too long
- **Background tasks:** The agent can start servers and long processes non-blocking
- **Web search:** The agent can search DuckDuckGo and fetch URLs for documentation

## 📝 License

MIT — use it however you want.

---

<p align="center">
  <strong>Built with ❤️ and ⚡ NVIDIA's free API</strong><br>
  <em>Hosted planning plus guarded local execution.</em>
</p>
