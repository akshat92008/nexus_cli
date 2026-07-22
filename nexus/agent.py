"""
Agent — the core agentic loop upgraded to a full Agent Operating System.

Integrates Planning, Reflection, Context Management, Safety, project rules (NEXUS.md),
user preferences, skills, subagents, hooks, MCP, and plugins.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from nexus.api import NvidiaClient
from nexus.models import resolve_model, DEFAULT_MODEL, MODELS
from nexus.tools import TOOL_DEFINITIONS, execute_tool, tool_get_project_structure, tool_git_status
from nexus.history import get_history, init_history
from nexus.memory import ConversationMemory, compact_messages

# Phase 1: Core Engine Imports
from nexus.planner import PlanningEngine, PlanType, TaskStatus, IntentType
from nexus.reflection import ReflectionEngine, ReflectionVerdict
from nexus.context_manager import ContextManager
from nexus.safety import SafetyLayer, SafetyLevel, SafetyCheck
from nexus.project_memory import ProjectMemory
from nexus.user_memory import UserMemory
from nexus.verification import VerificationEngine, CheckType

# Phase 2: Skills & Subagents
from nexus.skills.loader import SkillRegistry, SkillLoader
from nexus.subagents.orchestrator import SubagentOrchestrator
from nexus.subagents.templates import create_subagent

# Phase 3: Hooks, MCP & Plugins
from nexus.hooks.runner import HookRunner
from nexus.hooks.base import HookEvent, HookContext
from nexus.hooks.builtin import create_builtin_hooks
from nexus.mcp.client import MCPClient
from nexus.plugins.loader import PluginLoader

from nexus import ui


# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are NexusAI, an extremely powerful AI coding agent — a 10x senior engineer with full access to the user's system.
You operate through tool calls that let you read, write, edit, search, execute, and manage code with superhuman speed and precision.

## CORE IDENTITY
- You are decisive and action-oriented. When asked to build something, you BUILD it — completely, production-ready, no shortcuts.
- You proactively explore the codebase before making changes. Read first, understand, then act.
- You fix errors automatically. If your code fails, you diagnose and fix it without being asked.
- You use git to track your changes. Commit frequently with meaningful messages.

## YOUR 20 TOOLS

### File Operations
- `read_file(path, start_line?, end_line?)` — Read file contents with line numbers
- `write_file(path, content)` — Create or overwrite files (auto-creates directories)
- `edit_file(path, old_text, new_text)` — Surgical find-and-replace (old_text must be EXACT and unique)
- `patch_file(path, start_line, end_line, new_content)` — Line-range based editing
- `multi_edit(edits[])` — Batch edits across multiple files in one call
- `file_info(path)` — File metadata (size, type, permissions, line count, MD5)
- `diff_files(file_a, file_b)` — Unified diff between two files

### Code Search
- `search_code(pattern, directory?, file_pattern?)` — Regex search across codebase
- `list_directory(path?, recursive?, max_depth?)` — List directory contents
- `find_files(pattern, directory?)` — Glob-based file finder
- `get_project_structure(path?, max_depth?)` — Tree view of project

### Shell Execution
- `run_command(command, cwd?, timeout?)` — Execute any shell command (blocking)
- `process_run(command, cwd?)` — Start a background process (non-blocking, returns PID)

### Git Operations
- `git_status(cwd?)` — Full repo status (branch, staged, modified, untracked)
- `git_diff(target?, staged?, file_path?, cwd?)` — View diffs (working/staged/commits)
- `git_commit(message, files?, all?, cwd?)` — Stage and commit changes
- `git_log(count?, oneline?, file_path?, cwd?)` — View commit history
- `git_branch(action?, name?, cwd?)` — List/create/switch/delete branches

### Web
- `web_fetch(url, max_length?)` — Fetch and read any URL (strips HTML to text)
- `web_search(query, max_results?)` — Search the web via DuckDuckGo

## WORKFLOW PATTERNS

### Building a New Feature:
1. Read project structure and relevant files to understand the codebase
2. Plan the implementation approach
3. Write/edit files to implement the feature
4. Run the code to verify it works
5. Fix any errors automatically
6. Commit the changes with a meaningful message

### Debugging:
1. Read the error message and relevant code
2. Search for related patterns in the codebase
3. Identify the root cause
4. Apply the fix
5. Run tests to verify
6. If it still fails, iterate

### Code Review / Refactoring:
1. Read the files to understand current state
2. Identify improvements
3. Apply edits surgically using edit_file (NOT write_file for existing files)
4. Run tests to ensure nothing breaks

## RULES
1. **ALWAYS use edit_file for modifications** — never use write_file to modify existing files (you'll lose content you didn't read)
2. **Read before writing** — always read a file before editing it
3. **old_text must be EXACT** — copy the exact text including whitespace and indentation
4. **Run code after changes** — verify your changes work
5. **Handle errors gracefully** — if a tool fails, try a different approach
6. **Be thorough** — add error handling, types, docstrings, and tests
7. **Use modern patterns** — write idiomatic, production-quality code
8. **Multiple tools per turn** — you can call several tools in sequence within one turn
9. **Commit after major changes** — use git_commit to track your work
10. **Search before creating** — check if similar code already exists

## CODE QUALITY STANDARDS
- Python: type hints, docstrings, PEP 8, error handling, pathlib
- JavaScript/TypeScript: JSDoc, error handling, modern ES6+, async/await
- Go: error handling, go doc, gofmt
- Rust: proper error types, documentation, clippy-clean
- All: meaningful variable names, DRY, SOLID principles

When in doubt, ask the user. But when the task is clear, EXECUTE WITHOUT HESITATION."""


# ── Agent Class ──────────────────────────────────────────────────────────────

class Agent:
    """
    The core Agent Operating System — manages conversation, tool calls,
    streaming, planning, reflection, context, safety, skills, subagents,
    hooks, MCP, plugins, and memory.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_key: str = DEFAULT_MODEL,
        working_dir: str | None = None,
    ):
        self.working_dir = str(Path(working_dir or os.getcwd()).resolve())
        os.chdir(self.working_dir)

        # API Client
        self.client = NvidiaClient(api_key=api_key)
        self.model_key = model_key
        self.model_cfg = resolve_model(model_key) or MODELS[DEFAULT_MODEL]

        # State
        self.messages: list[dict] = []
        self.base_system_prompt = SYSTEM_PROMPT
        self.system_prompt = SYSTEM_PROMPT
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.conversation_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Legacy compatibility
        self.memory = ConversationMemory()
        self.history = init_history(self.conversation_id)
        self._context_gathered = False
        self._auto_fix_enabled = True
        self._auto_save_enabled = True

        # ── Phase 1: Core Engines ────────────────────────────────────────
        self.planner = PlanningEngine()
        self.reflector = ReflectionEngine()
        self.context_mgr = ContextManager(self.working_dir)
        self.safety = SafetyLayer()
        self.project_mem = ProjectMemory(self.working_dir)
        self.user_mem = UserMemory()
        self.verifier = VerificationEngine(self.working_dir)

        # ── Phase 2: Skills & Subagents ──────────────────────────────────
        self.skills = SkillRegistry()
        self._skill_loader = SkillLoader(self.skills)
        self._skill_loader.load_all()

        # ── Phase 3: Hooks Engine ────────────────────────────────────────
        self.hooks = HookRunner(self.working_dir)
        for hook in create_builtin_hooks():
            self.hooks.register(hook)

        # ── Phase 3: MCP Client ──────────────────────────────────────────
        self.mcp = MCPClient()
        try:
            self.mcp.load_default_config()
            self.mcp.connect_all()
        except Exception:
            pass  # MCP is optional

        # ── Phase 3: Plugins ─────────────────────────────────────────────
        self.plugin_loader = PluginLoader(self.working_dir)
        try:
            for plugin in self.plugin_loader.discover_and_load():
                for skill in plugin.get_skills():
                    self.skills.register(skill)
                for hook in plugin.get_hooks():
                    self.hooks.register(hook)
        except Exception:
            pass  # Plugins are optional

        # Load project rules and user preferences
        self._load_rules_and_preferences()

        # Build the full system prompt
        self._update_system_prompt()

        # Fire session start hook
        self.hooks.fire(HookEvent.ON_SESSION_START, HookContext(event=HookEvent.ON_SESSION_START))

    # ── Configuration ────────────────────────────────────────────────────

    def _load_rules_and_preferences(self):
        """Load project rules and user preferences, configuring safety layer."""
        try:
            rules = self.project_mem.load_rules()
            self.safety.configure_from_rules(self.project_mem.get_safety_config())

            # Sync verifier with project-specific commands
            custom_cmds = {}
            if rules.test_command:
                custom_cmds["test_command"] = rules.test_command
            if rules.lint_command:
                custom_cmds["lint_command"] = rules.lint_command
            if rules.build_command:
                custom_cmds["build_command"] = rules.build_command
            if rules.format_command:
                custom_cmds["format_command"] = rules.format_command
            if custom_cmds:
                self.verifier = VerificationEngine(self.working_dir, custom_cmds)
        except Exception:
            pass

    def _update_system_prompt(self):
        """Combine base prompt with project memory, user preferences, and active skills."""
        prompt = self.base_system_prompt

        # Project memory (NEXUS.md rules)
        try:
            addon = self.project_mem.get_prompt_addon()
            if addon:
                prompt += "\n" + addon
        except Exception:
            pass

        # User memory (persistent preferences)
        try:
            addon = self.user_mem.get_prompt_addon()
            if addon:
                prompt += "\n" + addon
        except Exception:
            pass

        # Active skills
        try:
            addon = self.skills.get_combined_prompt()
            if addon:
                prompt += "\n" + addon
        except Exception:
            pass

        # MCP tools description
        try:
            mcp_tools = self.mcp.get_all_tools()
            if mcp_tools:
                prompt += "\n\n[MCP CONNECTED TOOLS]\n"
                for t in mcp_tools:
                    prompt += f"  • {t.server_name}/{t.name} — {t.description}\n"
                prompt += "[END MCP TOOLS]"
        except Exception:
            pass

        self.system_prompt = prompt

    def set_model(self, model_key: str) -> bool:
        """Switch to a different model."""
        cfg = resolve_model(model_key)
        if not cfg:
            return False
        self.model_key = model_key
        self.model_cfg = cfg
        self.hooks.fire(HookEvent.ON_MODEL_SWITCH, HookContext(
            event=HookEvent.ON_MODEL_SWITCH,
            metadata={"model": model_key},
        ))
        return True

    def set_system_prompt(self, prompt: str):
        """Set a custom base system prompt."""
        self.base_system_prompt = prompt
        self._update_system_prompt()

    def clear_history(self):
        """Clear conversation history and deactivate skills."""
        self.messages = []
        self._context_gathered = False
        self.skills.deactivate_all()
        self.reflector.reset()
        self._update_system_prompt()

    def compact_conversation(self) -> int:
        """Compact the conversation by summarizing old messages."""
        old_count = len(self.messages)
        self.messages = compact_messages(self.messages, keep_recent=12)
        return old_count - len(self.messages)

    def load_conversation(self, conv_id: str) -> bool:
        """Load a conversation from memory."""
        data = self.memory.load_conversation(conv_id)
        if not data:
            return False
        self.messages = data.get("messages", [])
        self.conversation_id = data.get("id", conv_id)
        model_id = data.get("model_id", "")
        for key, cfg in MODELS.items():
            if cfg["id"] == model_id:
                self.model_key = key
                self.model_cfg = cfg
                break
        return True

    # ── Message Building ─────────────────────────────────────────────────

    def _gather_context(self) -> str:
        """Auto-gather project context on first interaction."""
        if self._context_gathered:
            return ""
        self._context_gathered = True

        # Use the new ContextManager for initialization
        try:
            return self.context_mgr.initialize()
        except Exception:
            pass

        # Fallback to legacy context gathering
        parts = []
        try:
            tree = tool_get_project_structure(self.working_dir, max_depth=3)
            if tree and len(tree) > 50:
                parts.append(f"[AUTO-CONTEXT: Project Structure]\n{tree}")
        except Exception:
            pass

        try:
            git_info = tool_git_status(self.working_dir)
            if git_info and "Not a git" not in git_info:
                parts.append(f"[AUTO-CONTEXT: Git Status]\n{git_info}")
        except Exception:
            pass

        config_files = [
            "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
            "Makefile", "Dockerfile", "docker-compose.yml", "tsconfig.json",
            ".eslintrc.json", "requirements.txt",
        ]
        found_configs = []
        for cf in config_files:
            p = Path(self.working_dir) / cf
            if p.exists():
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    if len(content) > 3000:
                        content = content[:3000] + "... (truncated)"
                    found_configs.append(f"--- {cf} ---\n{content}")
                except OSError:
                    pass

        if found_configs:
            parts.append("[AUTO-CONTEXT: Config Files]\n" + "\n\n".join(found_configs))

        if parts:
            return "\n\n".join(parts) + "\n\n---\n\n"
        return ""

    def _build_messages(self) -> list[dict]:
        """Build the full message list with system prompt and plan context."""
        cwd_info = f"\n\nCurrent working directory: {self.working_dir}"
        time_info = f"\nCurrent time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        os_info = f"\nOS: {sys.platform}"

        # Plan context injection
        plan_context = self.planner.get_plan_context()

        # Reflection context injection
        reflection_context = self.reflector.get_reflection_context()

        # Active file context
        active_context = self.context_mgr.get_relevant_context()

        system = {
            "role": "system",
            "content": (
                self.system_prompt
                + cwd_info + time_info + os_info
                + plan_context
                + reflection_context
                + ("\n" + active_context if active_context else "")
            ),
        }
        return [system] + self.messages

    def _get_tools(self) -> list[dict] | None:
        """Get tool definitions including built-in, plugin, and MCP tools."""
        if not self.model_cfg.get("supports_tools"):
            return None

        tools = list(TOOL_DEFINITIONS)

        # Plugin tools
        for plugin in self.plugin_loader.plugins.values():
            tools.extend(plugin.get_tools())

        # MCP tools
        try:
            tools.extend(self.mcp.get_all_tool_definitions())
        except Exception:
            pass

        return tools

    # ── Tool Execution (with safety, hooks, reflection) ──────────────────

    def _execute_tool_with_safety(self, name: str, args: dict) -> tuple[str, bool]:
        """
        Execute a tool with full safety checks, hooks, and context tracking.

        Pipeline: Before Hooks → Safety Check → Execute → Context Track → After Hooks → Reflection
        """
        from nexus.tools import normalize_tool_arguments
        args = normalize_tool_arguments(name, args)
        file_path = args.get("path", "") or args.get("file_path", "")
        command = args.get("command", "")

        # ── 1. Determine lifecycle events ────────────────────────────────
        event_before = None
        event_after = None

        if name in ("write_file",):
            event_before = HookEvent.BEFORE_FILE_CREATE
            event_after = HookEvent.AFTER_FILE_CREATE
        elif name in ("edit_file", "patch_file", "multi_edit"):
            event_before = HookEvent.BEFORE_FILE_EDIT
            event_after = HookEvent.AFTER_FILE_EDIT
        elif name in ("run_command", "process_run"):
            event_before = HookEvent.BEFORE_COMMAND
            event_after = HookEvent.AFTER_COMMAND
        elif name == "git_commit":
            event_before = HookEvent.BEFORE_COMMIT
            event_after = HookEvent.AFTER_COMMIT

        hook_ctx = HookContext(
            event=event_before or HookEvent.BEFORE_COMMAND,
            file_path=file_path,
            command=command,
            tool_name=name,
            tool_args=args,
        )

        # ── 2. Fire BEFORE hooks ─────────────────────────────────────────
        if event_before:
            hook_ctx.event = event_before
            hook_results = self.hooks.fire(event_before, hook_ctx)
            if any(r.blocked for r in hook_results):
                return "❌ Operation blocked by hook policy.", False

        # ── 3. Safety check ──────────────────────────────────────────────
        safety_check = None
        if name in ("run_command", "process_run") and command:
            safety_check = self.safety.check_command(command)
        elif name in ("write_file", "edit_file", "patch_file", "multi_edit") and file_path:
            content = args.get("content", "") or args.get("new_text", "") or args.get("new_content", "")
            safety_check = self.safety.check_file_write(file_path, content)
        elif name.startswith("git_"):
            safety_check = self.safety.check_git_operation([name] + [str(v) for v in args.values() if isinstance(v, str)])

        if safety_check and not safety_check.is_allowed:
            if safety_check.level == SafetyLevel.BLOCKED:
                return f"❌ BLOCKED: {safety_check.reason}", False
            # For DANGEROUS, the CLI run() method will handle user confirmation
            # For non-interactive, we allow it through
            if safety_check.level == SafetyLevel.WARN:
                pass  # Log warning but proceed

        # ── 4. Execute the tool ──────────────────────────────────────────
        result = ""

        # Check plugin tool dispatch first
        plugin_handled = False
        for plugin in self.plugin_loader.plugins.values():
            dispatch = plugin.get_tool_dispatch()
            if name in dispatch:
                try:
                    result = dispatch[name](**args)
                    plugin_handled = True
                except Exception as e:
                    result = f"❌ Plugin tool error: {e}"
                    plugin_handled = True
                break

        if not plugin_handled:
            if self.mcp.is_mcp_tool(name):
                result = self.mcp.call_tool(name, args)
            else:
                result = execute_tool(name, args)

        success = not result.startswith("❌")

        # ── 5. Track file access in context manager ──────────────────────
        if file_path:
            was_edited = name in ("write_file", "edit_file", "patch_file", "multi_edit")
            self.context_mgr.track_file_access(file_path, was_edited=was_edited)
            if success and name == "read_file" and result:
                self.context_mgr.track_file_imports(file_path, result)
                self.context_mgr.summarize_file(file_path, result)

        # ── 6. Fire AFTER hooks ──────────────────────────────────────────
        if event_after:
            hook_ctx.event = event_after
            hook_ctx.tool_result = result
            self.hooks.fire(event_after, hook_ctx)

        # ── 7. Fire error hook on failure ────────────────────────────────
        if not success:
            self.hooks.fire(HookEvent.ON_ERROR, HookContext(
                event=HookEvent.ON_ERROR,
                error_message=result[:500],
                tool_name=name,
                tool_args=args,
            ))

        return result, success

    def _format_live_tool_status(self, tool_calls_accum: dict[int, dict]) -> str:
        """Format real-time status message with line counts & byte counters while tool JSON streams."""
        if not tool_calls_accum:
            return f"[bold {ui.CYAN}]Thinking & Reasoning with {self.model_cfg['name']}...[/]"

        last_idx = max(tool_calls_accum.keys())
        tc = tool_calls_accum[last_idx]
        name = tc.get("name", "")
        raw_args = tc.get("arguments", "")

        import re
        m_path = re.search(r'"(?:path|file_path|file)"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)', raw_args)
        path_str = m_path.group(1) if m_path else ""

        m_cmd = re.search(r'"command"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)', raw_args)
        cmd_str = m_cmd.group(1) if m_cmd else ""

        lines = raw_args.count('\n') + raw_args.count('\\n')
        chars = len(raw_args)

        if name in ("write_file", "create_file"):
            if path_str:
                return f"[bold {ui.ORANGE}]⚡ Stream-Drafting File:[/] [bold {ui.CYAN}]{path_str}[/] [bold {ui.GOLD}]({lines} lines / {chars:,} bytes)[/]"
            return f"[bold {ui.ORANGE}]⚡ Stream-Drafting Code File...[/] [bold {ui.GOLD}]({lines} lines / {chars:,} bytes)[/]"

        elif name in ("edit_file", "patch_file", "multi_edit"):
            if path_str:
                return f"[bold {ui.ORANGE}]⚡ Surgical Code Edit:[/] [bold {ui.CYAN}]{path_str}[/] [bold {ui.GOLD}]({lines} lines / {chars:,} bytes)[/]"
            return f"[bold {ui.ORANGE}]⚡ Preparing Surgical Code Edit...[/] [bold {ui.GOLD}]({chars:,} bytes)[/]"

        elif name in ("run_command", "process_run"):
            if cmd_str:
                clean_cmd = cmd_str.replace("\\n", " ").replace("\n", " ")
                return f"[bold {ui.ORANGE}]⚡ Sandbox Shell Execution:[/] [bold {ui.WHITE}]{clean_cmd[:65]}[/]"
            return f"[bold {ui.ORANGE}]⚡ Preparing Sandbox Shell Execution...[/]"

        elif name:
            return f"[bold {ui.ORANGE}]⚡ Executing Tool Matrix:[/] [bold {ui.CYAN}]{name}[/] [bold {ui.GOLD}]({chars:,} bytes)[/]"

        return f"[bold {ui.CYAN}]Thinking & Reasoning with {self.model_cfg['name']}...[/]"

    def _handle_tool_calls_interactive(self, tool_calls: list[dict]) -> list[dict]:
        """Execute tool calls with UI output and return tool result messages."""
        results = []
        for tc in tool_calls:
            name = tc["name"]
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}

            ui.print_tool_call(name, args)

            exec_msg = f"Executing {name}..."
            if name == "write_file":
                path_val = args.get("path", "")
                content_val = args.get("content", "") or ""
                lines_cnt = content_val.count("\n") + 1 if content_val else 0
                exec_msg = f"Writing {lines_cnt} lines to {path_val}..."
            elif name in ("edit_file", "patch_file"):
                path_val = args.get("path", "")
                exec_msg = f"Applying edit to {path_val}..."
            elif name in ("run_command", "process_run"):
                cmd_val = args.get("command", "")
                exec_msg = f"Running command: {cmd_val[:60]}..."

            with ui.console.status(f"[bold {ui.ORANGE}]⚡ {exec_msg}[/]", spinner="bouncingBar"):
                result, success = self._execute_tool_with_safety(name, args)

            ui.print_tool_result(result, success)

            # Reflection
            verdict = self.reflector.reflect(name, args, result)
            if verdict.verdict == ReflectionVerdict.ESCALATE:
                ui.print_warning(f"⚠ Reflection: {verdict.suggestion}")

            results.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

        return results

    # ── Streaming Handler ────────────────────────────────────────────────

    def _handle_stream(self, stream) -> tuple[str, list[dict]]:
        """Handle a streaming response with real-time text and tool-drafting status feedback."""
        full_content = ""
        tool_calls_accum: dict[int, dict] = {}
        prompt_tokens = 0
        completion_tokens = 0

        live = ui.LiveStatus()
        live.start("Thinking...")
        has_printed_text = False
        tool_stream_started = False
        last_ui_update = 0.0

        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Stream text content
                if delta.content:
                    if live._is_active:
                        live.stop()
                    ui.console.print(delta.content, end="", style=ui.WHITE, highlight=False)
                    full_content += delta.content
                    has_printed_text = True

                # Accumulate and preview tool calls in real time
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_accum:
                            tool_calls_accum[idx] = {
                                "id": tc.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_calls_accum[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_accum[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_accum[idx]["arguments"] += tc.function.arguments

                    # Update live tool status animation throttled to 100ms
                    if has_printed_text and not tool_stream_started:
                        ui.console.print()  # Add newline so status doesn't overwrite text
                        tool_stream_started = True

                    now = time.time()
                    if now - last_ui_update > 0.1:
                        status_msg = self._format_live_tool_status(tool_calls_accum)
                        live.update(status_msg)
                        last_ui_update = now

                if hasattr(chunk, "usage") and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens or 0
                    completion_tokens = chunk.usage.completion_tokens or 0
        finally:
            live.stop()

        if prompt_tokens:
            self.total_prompt_tokens += prompt_tokens
        if completion_tokens:
            self.total_completion_tokens += completion_tokens

        tool_calls = []
        for idx in sorted(tool_calls_accum.keys()):
            tc = tool_calls_accum[idx]
            if tc["name"]:
                if not tc.get("id"):
                    tc["id"] = f"call_{idx}_{int(time.time()*1000)}"
                tool_calls.append(tc)

        if full_content:
            ui.console.print()  # Newline after streamed content

        return full_content, tool_calls

    def _handle_tool_calls_interactive(self, tool_calls: list[dict]) -> list[dict]:
        """Execute tool calls with UI output and return tool result messages."""
        results = []
        for tc in tool_calls:
            name = tc["name"]
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}

            ui.print_tool_call(name, args)

            exec_msg = f"Executing {name}..."
            if name == "write_file":
                path_val = args.get("path", "")
                content_val = args.get("content", "") or ""
                lines_cnt = content_val.count("\n") + 1 if content_val else 0
                exec_msg = f"Writing {lines_cnt} lines to {path_val}..."
            elif name in ("edit_file", "patch_file"):
                path_val = args.get("path", "")
                exec_msg = f"Applying edit to {path_val}..."
            elif name in ("run_command", "process_run"):
                cmd_val = args.get("command", "")
                exec_msg = f"Running command: {cmd_val[:60]}..."

            with ui.console.status(f"[bold {ui.ORANGE}]⚡ {exec_msg}[/]", spinner="bouncingBar"):
                result, success = self._execute_tool_with_safety(name, args)

            ui.print_tool_result(result, success)

            # Reflection
            verdict = self.reflector.reflect(name, args, result)
            if verdict.verdict == ReflectionVerdict.ESCALATE:
                ui.print_warning(f"⚠ Reflection: {verdict.suggestion}")

            # Cap tool content for context memory efficiency
            truncated_res = result
            if len(result) > 6000:
                truncated_res = result[:3000] + f"\n\n... [truncated {len(result) - 6000} chars for context efficiency] ...\n\n" + result[-3000:]

            results.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": truncated_res,
            })

        return results

    # ── Main Run Loop (Interactive CLI) ──────────────────────────────────

    def run(self, user_input: str) -> str:
        """
        Run one turn of the agent loop with full OS integration.

        Pipeline:
        1. Gather context → 2. Analyze intent → 3. Activate skills →
        4. Create plan (if complex) → 5. Execute with safety + hooks + reflection →
        6. Verify plan completion
        """
        # Reload project rules on each turn
        self._load_rules_and_preferences()

        # Auto-gather context on first interaction
        context = self._gather_context()

        # ── 1. Analyze intent and activate skills ────────────────────────
        analysis = self.planner.analyze(user_input)

        activated = self.skills.auto_activate(
            user_input,
            intent=analysis["intent"].value if hasattr(analysis["intent"], "value") else str(analysis["intent"]),
        )
        if activated:
            skill_names = ", ".join(s.name for s in activated)
            ui.print_info(f"Skills activated: {skill_names}")
            self._update_system_prompt()

        # ── 2. Create plan if task is complex ────────────────────────────
        plan = None
        if analysis["plan_type"] == PlanType.PLANNED:
            plan = self.planner.create_plan(user_input, analysis)
            ui.console.print()
            ui.console.print(plan.format_summary())
            ui.console.print()

        # ── 3. Build the user message ────────────────────────────────────
        if context:
            augmented_input = context + "User request: " + user_input
        else:
            augmented_input = user_input

        self.messages.append({"role": "user", "content": augmented_input})

        # ── 4. Agentic loop ──────────────────────────────────────────────
        max_iterations = 50
        iteration = 0
        _rate_limit_retries = 0
        _max_rate_limit_retries = 5

        while iteration < max_iterations:
            iteration += 1

            try:
                live = ui.LiveStatus()
                live.start(f"Connecting to {self.model_cfg['name']}...")
                try:
                    stream = self.client.chat(
                        model_id=self.model_cfg["id"],
                        messages=self._build_messages(),
                        tools=self._get_tools(),
                        stream=True,
                    )
                finally:
                    live.stop()

                content, tool_calls = self._handle_stream(stream)
                _rate_limit_retries = 0  # Reset on success

            except Exception as e:
                error_msg = str(e)
                is_rate_limit = (
                    "429" in error_msg
                    or "rate" in error_msg.lower()
                    or "resourceexhausted" in error_msg.lower()
                    or "resource_exhausted" in error_msg.lower()
                    or "too many requests" in error_msg.lower()
                    or "request limit" in error_msg.lower()
                )
                is_context_overflow = (
                    "context" in error_msg.lower()
                    or "maximum context" in error_msg.lower()
                    or "token limit" in error_msg.lower()
                )
                is_timeout = (
                    "timed out" in error_msg.lower()
                    or "timeout" in error_msg.lower()
                    or "504" in error_msg
                    or "502" in error_msg
                )

                # Compact conversation on context overflow
                if is_context_overflow:
                    ui.print_warning("Context budget exceeded — compacting conversation history...")
                    self.compact_conversation()
                    iteration -= 1
                    continue

                # Try switching fallback API key or provider
                if is_rate_limit or is_timeout or "401" in error_msg or "Unauthorized" in error_msg or "500" in error_msg:
                    if self.client.switch_to_fallback():
                        ui.print_info("Switched to fallback API key...")
                        iteration -= 1
                        continue

                # Auto-retry with exponential backoff for rate limits or transient errors
                if (is_rate_limit or is_timeout) and _rate_limit_retries < _max_rate_limit_retries:
                    _rate_limit_retries += 1
                    wait_time = min(2 ** _rate_limit_retries, 15)
                    ui.print_warning(
                        f"API delayed/rate-limited — retrying ({_rate_limit_retries}/{_max_rate_limit_retries})..."
                    )
                    time.sleep(wait_time)
                    iteration -= 1
                    continue

                if "401" in error_msg or "Unauthorized" in error_msg:
                    ui.print_error("Invalid API key. Check your NVIDIA_API_KEY / GROQ_API_KEY.")
                elif is_rate_limit:
                    ui.print_error("Rate limited after multiple retries. Wait a moment and try again.")
                elif "404" in error_msg:
                    ui.print_error(f"Model '{self.model_cfg['id']}' not found. Try /models to switch.")
                else:
                    ui.print_error(f"API error: {error_msg}")

                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                return ""

            # If there are tool calls, execute them and loop
            if tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                self.messages.append(assistant_msg)

                # Execute with safety, hooks, and reflection
                tool_results = self._handle_tool_calls_interactive(tool_calls)
                self.messages.extend(tool_results)

                # Advance plan if active
                if plan:
                    next_step = plan.next_step
                    if next_step:
                        all_success = all(
                            not r["content"].startswith("❌")
                            for r in tool_results
                        )
                        self.planner.advance_step(
                            next_step.id,
                            TaskStatus.COMPLETED if all_success else TaskStatus.FAILED,
                        )

                continue

            # No tool calls — we're done
            if content:
                self.messages.append({"role": "assistant", "content": content})

            ui.print_response_complete()

            # ── 5. Post-plan verification ────────────────────────────────
            if plan and plan.is_complete:
                ui.print_info("📋 Plan complete. Running verification...")
                try:
                    report = self.verifier.run_all()
                    ui.console.print(report.format_report())
                    if report.all_passed:
                        self.hooks.fire(HookEvent.ON_PLAN_COMPLETE, HookContext(event=HookEvent.ON_PLAN_COMPLETE))
                    else:
                        self.hooks.fire(HookEvent.ON_TEST_FAIL, HookContext(event=HookEvent.ON_TEST_FAIL))
                except Exception:
                    pass

            self._auto_save()
            return content or ""

        ui.print_warning("Reached maximum tool-call iterations (safety limit).")
        self._auto_save()
        return ""

    # ── Non-Interactive Run (Web API) ────────────────────────────────────

    def run_non_interactive(self, user_input: str) -> tuple[str, list[dict]]:
        """
        Run one turn and return (final_text, all_tool_events).
        Used by the web API for structured responses.
        """
        events: list[dict] = []

        # Auto-gather context
        context = self._gather_context()
        if context:
            augmented_input = context + "User request: " + user_input
        else:
            augmented_input = user_input

        # Auto-activate skills
        try:
            analysis = self.planner.analyze(user_input)
            self.skills.auto_activate(
                user_input,
                intent=analysis["intent"].value if hasattr(analysis["intent"], "value") else str(analysis["intent"]),
            )
            self._update_system_prompt()
        except Exception:
            pass

        self.messages.append({"role": "user", "content": augmented_input})

        max_iterations = 50
        iteration = 0
        final_content = ""

        while iteration < max_iterations:
            iteration += 1

            try:
                response = self.client.chat_sync(
                    model_id=self.model_cfg["id"],
                    messages=self._build_messages(),
                    tools=self._get_tools(),
                )

                choice = response.choices[0]
                content = choice.message.content or ""
                tool_calls_raw = choice.message.tool_calls or []

                if hasattr(response, "usage") and response.usage:
                    self.total_prompt_tokens += response.usage.prompt_tokens or 0
                    self.total_completion_tokens += response.usage.completion_tokens or 0

            except Exception as e:
                error_msg = str(e)
                if ("401" in error_msg or "429" in error_msg or "Unauthorized" in error_msg or "rate" in error_msg.lower()):
                    if self.client.switch_to_fallback():
                        iteration -= 1
                        continue
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                return f"Error: {error_msg}", events

            # Process tool calls
            if tool_calls_raw:
                tool_calls = []
                for tc in tool_calls_raw:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    })

                # Add assistant message
                assistant_msg = {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in tool_calls
                    ],
                }
                self.messages.append(assistant_msg)

                # Execute tools with safety
                for tc in tool_calls:
                    name = tc["name"]
                    try:
                        args = json.loads(tc["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    result, success = self._execute_tool_with_safety(name, args)

                    events.append({
                        "type": "tool_call",
                        "name": name,
                        "args": args,
                        "result": result,
                        "success": success,
                    })

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })

                continue

            # No tool calls — done
            if content:
                self.messages.append({"role": "assistant", "content": content})

            final_content = content
            self._auto_save()
            break

        return final_content, events

    # ── Subagent Integration ─────────────────────────────────────────────

    def spawn_subagent(self, template_name: str, task: str) -> str:
        """Spawn a subagent from a template and execute its task."""
        subagent = create_subagent(template_name, task, self.working_dir)
        if not subagent:
            return f"❌ Unknown subagent template: {template_name}"

        orchestrator = SubagentOrchestrator(
            api_key=self.client._api_key,
            model_id=self.model_cfg["id"],
            working_dir=self.working_dir,
        )
        result = orchestrator.run_single(subagent)

        self.hooks.fire(HookEvent.ON_SUBAGENT_COMPLETE, HookContext(
            event=HookEvent.ON_SUBAGENT_COMPLETE,
            metadata={"subagent": template_name, "task": task},
        ))

        return result.format_report()

    def run_verification(self, checks: list[str] | None = None) -> str:
        """Run verification checks and return the report."""
        check_types = None
        if checks:
            check_types = [CheckType(c) for c in checks if c in CheckType.__members__.values()]
        report = self.verifier.run_all(check_types)
        return report.format_report()

    # ── Persistence ──────────────────────────────────────────────────────

    def _auto_save(self):
        """Auto-save the conversation."""
        if self._auto_save_enabled and len(self.messages) >= 2:
            try:
                self.memory.auto_save(
                    self.messages,
                    self.model_cfg["name"],
                    self.model_cfg["id"],
                    self.working_dir,
                    self.conversation_id,
                )
            except Exception:
                pass

    def save_conversation(self, filepath: str):
        """Save the conversation to a JSON file."""
        data = {
            "model": self.model_cfg["name"],
            "model_id": self.model_cfg["id"],
            "timestamp": datetime.now().isoformat(),
            "messages": self.messages,
        }
        p = Path(filepath).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(data, f, indent=2)
        ui.print_success(f"Conversation saved to {p}")
