<h1 align="center">
  ⚡ NexusAI v2.0
</h1>

<p align="center">
  <strong>A Claude-Code-level AI coding agent — CLI + Web Interface</strong><br>
  <em>20 Tools • Git Integration • Web Search • Undo/Diff • Conversation Memory • Free API</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/NVIDIA-API%20Catalog-76B900?style=for-the-badge&logo=nvidia" />
  <img src="https://img.shields.io/badge/Tools-20-blue?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Cost-FREE-green?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Python-3.10+-yellow?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/Interface-CLI%20%2B%20Web-purple?style=for-the-badge" />
</p>

---

## 🚀 What is NexusAI?

NexusAI is a **Claude-Code-level AI coding agent** powered by [NVIDIA's free API catalog](https://build.nvidia.com). It has **20 built-in tools**, full **git integration**, **web search**, **undo/diff tracking**, **conversation memory**, and both a **terminal CLI** and a **stunning Cursor-like web interface**.

### Why NexusAI?
- 🆓 **Completely free** — NVIDIA's API catalog has no usage costs
- 🛠️ **20 powerful tools** — files, git, shell, web search, multi-edit
- 🧠 **Smart context** — auto-reads project structure, git status, config files
- ↩️ **Undo system** — every file change is tracked and reversible
- 💾 **Memory** — conversations persist across sessions
- 🌐 **Two interfaces** — terminal CLI + premium web UI
- 🤖 **14+ AI models** — switch models mid-conversation

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

# Web Interface (Cursor-like UI)
python run.py --web

# Web Interface on custom port
python run.py --web --port 8080
```

Or install as a CLI tool:
```bash
pip install -e .

# CLI mode
nexus

# Web mode
nexus --web
```

### 3. One-Line Launcher
```bash
bash nexus.sh           # CLI mode (auto-installs deps)
bash nexus.sh --web     # Web mode
```

## 🛠️ 20 Agent Tools

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
| `/model <name>` | Switch models (e.g., `/model kimi`) |
| `/tools` | List all 20 agent tools |
| `/git` | Show git status |
| `/undo` | Undo the last file change |
| `/diff` | Show the last change as a diff |
| `/changes` | List all file changes this session |
| `/history` | List saved conversations |
| `/resume <id>` | Resume a previous conversation |
| `/compact` | Compress conversation to save context |
| `/clear` | Clear conversation history |
| `/reset` | Reset session and clear screen |
| `/project` | Show project structure |
| `/cost` | Show token usage stats |
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
- **Model selector** — switch between 14+ models from a dropdown
- **Code syntax highlighting** — with copy buttons and language labels
- **Responsive design** — works on desktop and mobile
- **Keyboard shortcuts** — Enter to send, Shift+Enter for new line

## 📦 Available Models (All Free!)

| Model | Category | Context | Best For |
|-------|----------|---------|----------|
| **DeepSeek V4 Pro** | Reasoning | 131K | Complex reasoning & coding |
| **DeepSeek R1** | Reasoning | 131K | Chain-of-thought reasoning |
| **GLM 5.2** | Reasoning | 131K | Agentic tasks & reasoning |
| **Kimi K2.6** | Coding | 131K | Long-horizon coding & tool use |
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
│   ├── cli.py                   # CLI entry point & REPL (19 commands)
│   ├── agent.py                 # Core agent: auto-context, auto-save, 50-iter loop
│   ├── api.py                   # NVIDIA API client (OpenAI-compatible)
│   ├── models.py                # Model registry & aliases (14+ models)
│   ├── tools.py                 # 20 tools: file, git, shell, web, search
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
  <em>No credit card. No limits. Just code.</em>
</p>
