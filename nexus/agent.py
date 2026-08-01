"""
Agent — the core agentic loop upgraded to a full Agent Operating System.

Integrates Planning, Reflection, Context Management, Safety, project rules (NEXUS.md),
user preferences, skills, subagents, hooks, MCP, and plugins.
"""

import json
import logging
import os
import re
import shlex
import sys
import time
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from nexus import ui
from nexus.approvals import preview_mutation
from nexus.budget import BudgetController, BudgetedClient, BudgetExceeded, BudgetLimits
from nexus.code_validation import GeneratedCodeValidator
from nexus.context_manager import ContextManager
from nexus.evidence import EvidenceTrail, command_exit_code, verify_mutation
from nexus.extensions import ExtensionRegistry, ToolContext
from nexus.history import FileHistory
from nexus.hooks.base import HookContext, HookEvent
from nexus.hooks.builtin import create_builtin_hooks

# Phase 3: Hooks, MCP & Plugins
from nexus.hooks.runner import HookRunner
from nexus.mcp.client import MCPClient
from nexus.memory import ConversationMemory, compact_messages
from nexus.models import DEFAULT_MODEL, MODELS, resolve_model, resolve_model_key
from nexus.package_guard import PackageGuard
from nexus.paths import nexus_home

# Phase 1: Core Engine Imports
from nexus.planner import IntentType, PlanningEngine, TaskStatus, TaskType, get_task_type
from nexus.plugins.loader import PluginLoader
from nexus.policy import ModePolicy, PermissionDecision, PolicyLoader, get_mode_policy
from nexus.project_memory import ProjectMemory
from nexus.providers.hosted import HostedProvider
from nexus.providers.nova import NovaProvider
from nexus.providers.router import FallbackRouter
from nexus.reflection import ReflectionEngine, ReflectionVerdict
from nexus.repo_graph import RepoGraph
from nexus.run_catalog import RunCatalog
from nexus.run_state import CriterionResult, CriterionStatus, RunLedger, RunStatus
from nexus.runtime.events import EventType
from nexus.runtime.session import ExecutionSession
from nexus.safety import SafetyCheck, SafetyLayer, SafetyLevel

# Phase 2: Skills & Subagents
from nexus.skills.loader import SkillLoader, SkillRegistry
from nexus.subagents.orchestrator import SubagentOrchestrator
from nexus.subagents.templates import create_subagent
from nexus.tools import TOOL_DEFINITIONS, execute_tool, tool_get_project_structure, tool_git_status
from nexus.trust import TrustStore
from nexus.user_memory import UserMemory
from nexus.verification import CheckStatus, CheckType, VerificationEngine
from nexus.workspace import GitWorktreeSession, WorktreeError


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _redact_runtime_text(value: str) -> str:
    """Remove common credential forms before persisting run summaries."""
    redacted = re.sub(
        r"(?i)\b(api[_-]?key|token|password|passwd|secret)\s*=\s*[^\s]+",
        r"\1=[REDACTED]",
        value,
    )
    return re.sub(
        r"\b(?:sk|gsk|nvapi|ghp)_[A-Za-z0-9_-]{8,}\b"
        r"|\b(?:sk|gsk|nvapi)-[A-Za-z0-9_-]{8,}\b",
        "[REDACTED_CREDENTIAL]",
        redacted,
    )


def _effective_evidence(evidence: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    """Return the latest state-bearing evidence instead of stale failed attempts."""

    matching = [item for item in evidence if item.get("kind") == kind]
    if kind == "verification_check":
        latest: dict[str, dict[str, Any]] = {}
        for item in matching:
            identity = str(
                item.get("metadata", {}).get("check_type") or item.get("command") or item.get("id")
            )
            latest[identity] = item
        return list(latest.values())
    if kind == "file_mutation":
        latest_by_path: dict[str, dict[str, Any]] = {}
        pathless: list[dict[str, Any]] = []
        for item in matching:
            paths = {
                str(artifact.get("path", ""))
                for artifact in item.get("artifacts", [])
                if artifact.get("path")
            }
            if not paths:
                pathless.append(item)
            for path in paths:
                latest_by_path[path] = item
        selected_ids = {str(item.get("id")) for item in latest_by_path.values()}
        return [
            item for item in matching if str(item.get("id")) in selected_ids or item in pathless
        ]
    return matching


# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are NexusAI, a coding agent with scoped access to the user's current workspace.
You use tool calls to inspect, edit, search, execute, and manage code while respecting the safety layer and user confirmation boundaries.

## CORE IDENTITY
- You are decisive and action-oriented. When asked to build something, you BUILD it — completely, production-ready, no shortcuts.
- You proactively explore the codebase before making changes. Read first, understand, then act.
- You fix errors automatically. If your code fails, you diagnose and fix it without being asked.
- You never claim success from your own prose. Completion requires literal tool output and a Nexus evidence record.
- File edits may be held as diff previews. If a tool returns PENDING_EDIT, tell the user which approval ID is waiting; do not claim the change was applied.

## YOUR ENGINEERING TOOLS

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
- `repo_index(force?)` — Build or refresh the persistent repository graph
- `repo_symbols(query, include_callers?, limit?)` — Find declarations and callers
- `repo_impact(paths[])` — Find reverse dependencies and impacted tests
- `repo_context(query)` — Rank task-relevant files using symbols, routes, models and Git
- `repo_routes(query?)` / `repo_models(query?)` — Inspect application topology

### Shell Execution
- `run_process(argv[], cwd?, timeout?, network?)` — Preferred shell-free sandboxed process
- `run_command(command, cwd?, timeout?)` — Reviewed compatibility shell command
- `process_run(command, cwd?)` — Start a background process (non-blocking, returns PID)

### Behavioural Verification
- `api_check(...)` — Validate a local HTTP contract
- `database_check(path)` — Validate SQLite integrity and foreign keys read-only
- `browser_check(...)` — Run an optional Playwright workflow
- `security_scan(paths?)` — Deterministic security pattern scan

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
6. Report the real verification output; commit only when the user requested a commit

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
4. **Run code after changes** — verify your changes with real exit codes; never treat static inspection as a passing test
5. **Handle errors gracefully** — if a tool fails, try a different approach
6. **Be thorough** — add error handling, types, docstrings, and tests
7. **Use modern patterns** — write idiomatic, production-quality code
8. **Multiple tools per turn** — you can call several tools in sequence within one turn
9. **Never fabricate completion** — no "passed", "working", or "verified" claim without a recorded check
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
        mode_policy: ModePolicy | None = None,
        working_dir: str | None = None,
        permission_mode: str = "default",
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        additional_dirs: list[str] | None = None,
        max_turns: int = 50,
        workspace_isolation: bool = False,
        max_hosted_calls: int | None = None,
        max_provider_attempts: int | None = None,
        max_prompt_tokens: int | None = None,
        max_completion_tokens: int | None = None,
        max_cost_usd: float | None = None,
        input_price_per_million: float | None = None,
        output_price_per_million: float | None = None,
        model_id_override: str | None = None,
        local_intern_mode: str = "off",
        enable_nova_fallback: bool = False,
        plugins_enabled: bool = False,
        tools_enabled: bool = True,
    ):
        self.source_working_dir = str(Path(working_dir or os.getcwd()).resolve())
        self.conversation_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.worktree: GitWorktreeSession | None = None
        self.working_dir = self.source_working_dir
        # P0-3 FIX: Remove os.chdir(self.working_dir) to prevent global process state pollution
        self.mode_policy = mode_policy or get_mode_policy(permission_mode)

        # Model and backend selection
        resolved_key = resolve_model_key(model_key) or DEFAULT_MODEL
        self.model_key = resolved_key
        self.model_cfg = resolve_model(resolved_key) or dict(MODELS[resolved_key])
        if model_id_override:
            self.model_cfg["id"] = model_id_override.strip()
            if self.model_key == "custom":
                self.model_cfg["name"] = f"Custom Hosted Model ({model_id_override.strip()})"
        if self.model_key == "custom" and not self.model_cfg.get("id"):
            raise ValueError("Custom hosted models require --model-id or NEXUS_MODEL_ID.")
        if not tools_enabled:
            self.model_cfg["supports_tools"] = False
        self._api_key = api_key
        self.local_intern_mode = str(local_intern_mode or "off").lower()
        if self.local_intern_mode not in {"off", "auto", "required"}:
            raise ValueError("local_intern_mode must be off, auto, or required")
        self.enable_nova_fallback = bool(enable_nova_fallback)
        self.local_intern_probe = None
        self.local_intern_enabled = False
        if not self.model_cfg.get("backend") == "nova" and self.local_intern_mode != "off":
            from nexus.preflight import probe_ollama

            self.local_intern_probe = probe_ollama(self.model_cfg.get("intern_model", "nova_codex"))
            self.local_intern_enabled = self.local_intern_probe.ready
            if self.local_intern_mode == "required" and not self.local_intern_enabled:
                raise ValueError(self.local_intern_probe.format())
        self.budget = BudgetController(
            BudgetLimits(
                max_hosted_calls=max_hosted_calls,
                max_provider_attempts=max_provider_attempts,
                max_prompt_tokens=max_prompt_tokens,
                max_completion_tokens=max_completion_tokens,
                max_cost_usd=max_cost_usd,
                input_price_per_million=input_price_per_million,
                output_price_per_million=output_price_per_million,
            )
        )
        hosted_client = None
        if not self._is_nova_model():
            primary = HostedProvider(
                api_key=api_key,
                attempt_controller=self.budget,
                attempt_observer=self._record_provider_attempt,
            )
            router = FallbackRouter(primary)
            from nexus.budget import BudgetedClient

            # BudgetedClient duck-types the provider to add budget enforcement
            hosted_client = BudgetedClient(router, self.budget)

        # Validate provider configuration and budgets before allocating a
        # persistent worktree so constructor failures cannot leak workspaces.
        if workspace_isolation:
            try:
                self.worktree = GitWorktreeSession(
                    self.source_working_dir,
                    self.conversation_id,
                )
                worktree_info = self.worktree.create()
                self.working_dir = worktree_info.path
            except WorktreeError as exc:
                raise ValueError(f"Could not create isolated Git worktree: {exc}") from exc
        if self._is_nova_model():
            try:
                self.client = NovaProvider(
                    model_name=self.model_cfg.get("ollama_model", "nova_codex"),
                    working_dir=self.working_dir,
                )
            except Exception:
                if self.worktree is not None:
                    self.worktree.discard()
                raise
        else:
            self.client = hosted_client

        # State
        self.messages: list[dict] = []
        self.base_system_prompt = SYSTEM_PROMPT
        self.system_prompt = SYSTEM_PROMPT
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.permission_mode = permission_mode
        self.allowed_tools = set(allowed_tools or [])
        self.disallowed_tools = set(disallowed_tools or [])
        self.additional_dirs = [
            str(Path(item).expanduser().resolve()) for item in (additional_dirs or [])
        ]
        self.max_turns = max(1, int(max_turns))

        # Legacy compatibility
        self.memory = ConversationMemory()
        self.history = FileHistory(self.conversation_id)
        self._context_gathered = False
        self._auto_fix_enabled = True
        self._auto_save_enabled = True
        self._pending_confirmations: dict[str, dict[str, Any]] = {}
        self._next_confirmation_id = 1
        self._pending_edits: dict[str, dict[str, Any]] = {}
        self._next_edit_id = 1
        self.evidence = EvidenceTrail(self.conversation_id)
        self.run_ledger = RunLedger(self.conversation_id, self.working_dir)
        self._run_history_start = 0
        self._active_objective = ""
        self._active_analysis: dict[str, Any] = {}
        self._active_plan = None
        self._enforce_plan_tool_contract = False
        self._permissions_used: set[str] = set()
        self._network_calls: list[str] = []
        self.package_guard = PackageGuard()
        self.trust = TrustStore(self.working_dir)
        self.policy = PolicyLoader(self.working_dir).load()
        self.extensions = ExtensionRegistry()
        self.extensions.discover()
        self.routing_stats = {
            "nova_tasks": 0,
            "ceiling_tasks": 0,
            "nova_retries": 0,
            "escalations": 0,
        }

        # ── Phase 1: Core Engines ────────────────────────────────────────
        self.planner = PlanningEngine()
        self.reflector = ReflectionEngine()
        self.context_mgr = ContextManager(self.working_dir)
        self.repo_graph = RepoGraph(self.working_dir)
        self.safety = SafetyLayer()
        self.project_mem = ProjectMemory(self.working_dir)
        self.user_mem = UserMemory()
        self.verifier = VerificationEngine(self.working_dir)

        # ── Phase 2: Skills & Subagents ──────────────────────────────────
        self.skills = SkillRegistry()
        self._skill_loader = SkillLoader(
            self.skills,
            self.working_dir,
            trusted=self.trust.is_approved,
        )
        self._skill_loader.load_all()
        for extension_skill in self.extensions.loaded("skills"):
            self.skills.register(extension_skill)

        # ── Phase 3: Hooks Engine ────────────────────────────────────────
        self.hooks = HookRunner(self.working_dir)
        for hook in create_builtin_hooks():
            self.hooks.register(hook)

        # ── Phase 3: MCP Client ──────────────────────────────────────────
        self.mcp = MCPClient()
        try:
            mcp_config = nexus_home() / "mcp_servers.json"
            if mcp_config.exists() and self.trust.is_approved(mcp_config):
                self.mcp.load_from_config(str(mcp_config))
                self.mcp.connect_all()
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            logging.getLogger(__name__).warning("MCP initialization failed: %s", exc)

        # ── Phase 3: Plugins (SECURITY: disabled by default) ─────────────
        self._plugins_enabled = bool(plugins_enabled)
        self.plugin_loader = PluginLoader(
            self.working_dir,
            plugins_enabled=self._plugins_enabled,
            trust_checker=self.trust.is_approved,
        )
        try:
            # SECURITY FIX: Eliminate all([]) bypass.
            # An empty generator `all(x for x in [])` returns True,
            # which would treat zero manifests as "all trusted".
            # We now require plugins_enabled=True AND explicit trust.
            for plugin in self.plugin_loader.discover_and_load():
                for skill in plugin.get_skills():
                    self.skills.register(skill)
                for hook in plugin.get_hooks():
                    self.hooks.register(hook)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Plugin loading failed: %s. Diagnostics: %s",
                exc,
                self.plugin_loader.get_diagnostics_summary(),
            )

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
            mcp_config = nexus_home() / "mcp_servers.json"
            if mcp_config.exists() and not self.trust.is_approved(mcp_config):
                self.mcp.disconnect_all()
            rules_paths = self.project_mem.get_rules_paths()
            if any(not self.trust.is_approved(path) for path in rules_paths):
                self.project_mem._rules = None
                self.safety.configure_from_rules({})
                return
            self.project_mem.reload()
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
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            logging.getLogger(__name__).debug("Failed to load project rules: %s", exc)
        except Exception as exc:
            logging.getLogger(__name__).warning("Unexpected error loading project rules: %s", exc)

    def _update_system_prompt(self):
        """Combine base prompt with project memory, user preferences, and active skills."""
        prompt = self.base_system_prompt

        # Project memory (NEXUS.md rules)
        try:
            rules_paths = self.project_mem.get_rules_paths()
            addon = (
                self.project_mem.get_prompt_addon()
                if not rules_paths or all(self.trust.is_approved(path) for path in rules_paths)
                else ""
            )
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

        # Repository Context
        try:
            if hasattr(self, "repo_graph") and self.repo_graph:
                import json

                summary = self.repo_graph.summary()
                prompt += "\n\n[REPOSITORY CONTEXT]\n"
                prompt += json.dumps(summary, indent=2)
                prompt += "\n[END REPOSITORY CONTEXT]"
        except Exception:
            pass

        self.system_prompt = prompt

    def set_model(self, model_key: str) -> bool:
        """Switch to a different model."""
        resolved_key = resolve_model_key(model_key)
        if not resolved_key:
            return False
        cfg = resolve_model(resolved_key) or dict(MODELS[resolved_key])
        if cfg.get("backend") == "nova":
            self.client = NovaProvider(
                model_name=cfg.get("ollama_model", "nova_codex"), working_dir=self.working_dir
            )
        else:
            try:
                primary = HostedProvider(
                    api_key=self._api_key,
                    attempt_controller=self.budget,
                    attempt_observer=self._record_provider_attempt,
                )
                router = FallbackRouter(primary)
                self.client = BudgetedClient(router, self.budget)
            except ValueError:
                return False
        self.model_key = resolved_key
        self.model_cfg = cfg
        self.hooks.fire(
            HookEvent.ON_MODEL_SWITCH,
            HookContext(
                event=HookEvent.ON_MODEL_SWITCH,
                metadata={"model": resolved_key},
            ),
        )
        return True

    def _is_nova_model(self) -> bool:
        """Return True when the active model uses the local Nova backend."""
        return self.model_cfg.get("backend") == "nova"

    def _should_use_two_node(self, analysis: dict) -> bool:
        """Use Ceiling+Intern for coding/workspace tasks handled by hosted models."""
        if (
            self._is_nova_model()
            or not self.model_cfg.get("supports_tools")
            or not self.local_intern_enabled
        ):
            return False
        intent = analysis.get("intent")
        return intent not in (IntentType.CHAT, IntentType.EXPLAIN, IntentType.SEARCH)

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

    def export_final_report(self) -> dict:
        """Return the final report dict for the current run.

        Reads ``final_report.json`` from the active run-turn directory.
        When no active turn is in progress, scans the session directory for the
        most recent turn and reads from there.

        Always returns a dict — never raises — so the CLI completion path can
        safely call this after ``Agent.run()`` regardless of what happened
        during the run.

        Returns:
            A dict with at minimum a ``"status"`` key. On success the dict
            contains all fields written by the verification/reporting layer.
            On failure it contains ``{"status": "UNVERIFIED", "error": "..."}``.
        """
        # 1. Try the active turn directory first
        turn_dir: Path | None = None
        try:
            turn_dir = self.run_ledger._require_turn()
        except Exception:
            pass

        # 2. Fall back to scanning session_dir for the most recently modified turn dir
        if turn_dir is None:
            try:
                session_dir = self.run_ledger.session_dir
                turn_dirs = sorted(
                    [d for d in session_dir.iterdir() if d.is_dir() and d.name.startswith("turn-")],
                    key=lambda d: d.name,
                    reverse=True,
                )
                if turn_dirs:
                    turn_dir = turn_dirs[0]
            except Exception:
                pass

        if turn_dir is None:
            return {
                "status": "UNVERIFIED",
                "error": "No run data found: no active or historical run turns exist",
            }

        report_path = turn_dir / "final_report.json"
        if not report_path.exists():
            return {
                "status": "UNVERIFIED",
                "error": "No final report generated for this run",
            }
        try:
            return json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "status": "UNVERIFIED",
                "error": f"Failed to read final report: {exc}",
            }

    def load_conversation(self, conv_id: str) -> bool:
        """Load a conversation from memory."""
        data = self.memory.load_conversation(conv_id)
        if not data:
            return False
        self.messages = data.get("messages", [])
        self.conversation_id = data.get("id", conv_id)
        self.history = FileHistory(self.conversation_id)
        self.evidence = EvidenceTrail(self.conversation_id)
        self.run_ledger = RunLedger(self.conversation_id, self.working_dir)
        resume = self.run_ledger.resume_summary()
        self._run_history_start = int(
            resume.get("request", {}).get("metadata", {}).get("history_start", 0)
        )
        self._active_objective = resume.get("request", {}).get("request", "")
        self._active_analysis = resume.get("request", {}).get("analysis", {})
        plan_data = resume.get("plan", {})
        if plan_data and plan_data.get("id"):
            try:
                from nexus.planner import ExecutionPlan

                self.planner.current_plan = ExecutionPlan.from_dict(plan_data)
                self._active_plan = self.planner.current_plan
            except (KeyError, TypeError, ValueError):
                self.planner.current_plan = None
                self._active_plan = None
        model_id = data.get("model_id", "")
        for key, cfg in MODELS.items():
            if cfg["id"] == model_id:
                self.model_key = key
                self.model_cfg = cfg
                break
        return True

    # ── Durable run lifecycle ───────────────────────────────────────────

    @staticmethod
    def _effective_evidence(evidence: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        return _effective_evidence(evidence, kind)

    def _applicable_verification(self, intent: IntentType, skills: list[str]) -> list[str]:
        """Generate checks that this repository can actually execute.

        Exact evidence matching remains strict; this only prevents Nexus from
        inventing a mandatory lint/type contract when the repository has no
        configured or installed linter/type checker.
        """

        generated = self.planner._generate_verification(intent, skills)
        available = {item.value for item in self.verifier.get_available_checks()}
        applicable: list[str] = []
        for item in generated:
            lowered = item.lower()
            if "lint/type" in lowered:
                if {"lint", "type_check"}.issubset(available):
                    applicable.append(item)
                elif "lint" in available:
                    applicable.append("Check for lint errors")
                elif "type_check" in available:
                    applicable.append("Check for type errors")
                continue
            applicable.append(item)
        return applicable

    def _begin_managed_run(
        self,
        user_input: str,
        analysis: dict[str, Any],
        plan=None,
    ) -> None:
        """Create the canonical run directory before model or tool activity."""
        self.budget.reset()
        objective_override = getattr(self, "_resume_objective_override", None)
        self._active_objective = objective_override or user_input
        self._resume_objective_override = None
        self._active_analysis = dict(analysis)
        self._active_plan = plan
        self._run_history_start = len(self.history.changes)
        self._turn_evidence_start = len(self.evidence.records())
        self._permissions_used = {f"permission_mode:{self.permission_mode}"}
        self._network_calls = []
        self.routing_stats = {
            "nova_tasks": 0,
            "ceiling_tasks": 0,
            "nova_retries": 0,
            "escalations": 0,
        }
        plan_record = plan or {
            "plan_type": "direct",
            "goal": user_input,
            "acceptance_criteria": self.planner._generate_acceptance_criteria(
                user_input,
                analysis["intent"],
                self._applicable_verification(
                    analysis["intent"],
                    analysis.get("skills_needed", []),
                ),
            ),
        }
        self.run_ledger.begin(
            self._active_objective,
            analysis=analysis,
            plan=plan_record,
            metadata={
                "model": self.model_key,
                "permission_mode": self.permission_mode,
                "workspace_isolated": self.worktree is not None,
                "source_working_dir": self.source_working_dir,
                "history_start": self._run_history_start,
            },
        )
        self.run_ledger.append_event(
            "run_started",
            status="verified",
            detail="Request and execution contract persisted before model execution.",
        )
        if plan and hasattr(plan, "steps"):
            current_step = (
                next(
                    (s for s in plan.steps if s.status == TaskStatus.IN_PROGRESS),
                    None,
                )
                or plan.next_step
            )
            if current_step and current_step.status == TaskStatus.PENDING:
                self.planner.advance_step(current_step.id, TaskStatus.IN_PROGRESS)

    def _record_provider_attempt(self, attempt: dict[str, Any]) -> None:
        """Persist one physical provider request emitted by the hosted router."""

        if not getattr(self, "run_ledger", None) or not self.run_ledger.turn_dir:
            return
        error = str(attempt.get("error", ""))
        error_category = ""
        if error:
            from nexus.runtime.kernel import classify_failure

            error_category = classify_failure(error).value
        usage = attempt.get("usage") if isinstance(attempt.get("usage"), dict) else {}
        limits = self.budget.snapshot().get("limits", {})
        input_price = limits.get("input_price_per_million")
        output_price = limits.get("output_price_per_million")
        estimated_cost = 0.0
        if input_price is not None and output_price is not None:
            estimated_cost = (
                int(usage.get("prompt_tokens", 0) or 0) * float(input_price)
                + int(usage.get("completion_tokens", 0) or 0) * float(output_price)
            ) / 1_000_000
        self.run_ledger.append_model_call(
            role="provider_attempt",
            model=str(attempt.get("model", self.model_cfg.get("id", ""))),
            provider=str(attempt.get("provider", "")),
            status=str(attempt.get("status", "failed")),
            usage=usage,
            request_id=str(attempt.get("request_id", "")),
            started_at=str(attempt.get("started_at", "")),
            completed_at=str(attempt.get("completed_at", "")),
            duration_ms=int(attempt.get("duration_ms", 0) or 0),
            attempt=int(attempt.get("attempt", 1) or 1),
            physical_attempt=int(attempt.get("physical_attempt", 1) or 1),
            retry_number=max(0, int(attempt.get("attempt", 1) or 1) - 1),
            fallback_from=str(attempt.get("fallback_from", "")),
            estimated_cost_usd=estimated_cost,
            error_category=error_category,
            detail=_redact_runtime_text(error[:1000]),
        )

    @staticmethod
    def _parse_review_payload(raw: str) -> dict[str, Any]:
        """Parse the reviewer's strict JSON response and fail closed."""

        candidate = (raw or "").strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
        if fenced:
            candidate = fenced.group(1)
        else:
            start, end = candidate.find("{"), candidate.rfind("}")
            if start >= 0 and end > start:
                candidate = candidate[start : end + 1]
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("approved"), bool):
            raise ValueError("review JSON must contain a boolean 'approved' field")
        findings = parsed.get("findings", [])
        if not isinstance(findings, list) or not all(isinstance(item, str) for item in findings):
            raise ValueError("review JSON 'findings' must be an array of strings")
        summary = parsed.get("summary", "")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("review JSON must contain a non-empty 'summary'")
        return {
            "approved": parsed["approved"],
            "summary": summary.strip(),
            "findings": findings,
        }

    def _run_independent_review(self) -> tuple[bool, str]:
        """Require a read-only hosted review before mutation runs can be verified."""

        evidence = self.evidence.records()[getattr(self, "_turn_evidence_start", 0) :]
        mutations = [item for item in evidence if item.get("kind") == "file_mutation"]
        if not mutations:
            return True, "No file mutations require independent review."
        approved = [
            item
            for item in evidence
            if item.get("kind") == "independent_review" and item.get("status") == "verified"
        ]
        if approved:
            return True, str(approved[-1].get("raw_output", "Independent review approved."))

        changes = self.history.changes[getattr(self, "_run_history_start", 0) :]
        diff = self.history.get_recent_diffs(max(1, len(changes)))
        if not diff or diff == "No file changes in this session.":
            message = "Independent review could not obtain the applied diff."
            self.evidence.append(
                kind="independent_review",
                claim="independent hosted reviewer evaluated the applied diff",
                status="failed",
                raw_output=message,
                metadata={"findings": [message]},
            )
            return False, message

        checks = [
            {
                "type": item.get("metadata", {}).get("check_type", ""),
                "status": item.get("status", ""),
                "claim": item.get("claim", ""),
            }
            for item in evidence
            if item.get("kind") == "verification_check"
        ]
        reviewer_model = os.environ.get("NEXUS_REVIEW_MODEL_ID", "").strip()
        if not reviewer_model and self.model_key == "custom":
            reviewer_model = self.model_cfg["id"]
        if not reviewer_model:
            reviewer_model = (
                "qwen/qwen3.5-397b-a17b"
                if self.model_cfg["id"] != "qwen/qwen3.5-397b-a17b"
                else "meta/llama-3.3-70b-instruct"
            )

        chunk_size = 50_000
        chunks = [diff[index : index + chunk_size] for index in range(0, len(diff), chunk_size)]
        all_findings: list[str] = []
        summaries: list[str] = []
        all_approved = True
        for index, chunk in enumerate(chunks, start=1):
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an independent, read-only senior code reviewer. Evaluate only "
                        "the supplied applied diff against the objective and deterministic check "
                        "results. Reject missing behavior, unsafe changes, broken integration, "
                        "unsupported completion claims, or an incomplete diff chunk. Return only "
                        'JSON: {"approved": boolean, "summary": string, '
                        '"findings": [string]}. Never request or call tools.'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Objective:\n{self._active_objective}\n\n"
                        f"Deterministic checks:\n{json.dumps(checks, ensure_ascii=False)}\n\n"
                        f"Diff chunk {index}/{len(chunks)}:\n```diff\n{chunk}\n```"
                    ),
                },
            ]
            started = datetime.now(timezone.utc)
            try:
                response = self.client.chat_sync(
                    model_id=reviewer_model,
                    messages=messages,
                    tools=None,
                    max_tokens=2000,
                    temperature=0.0,
                )
                raw = str(response.choices[0].message.content or "")
                parsed = self._parse_review_payload(raw)
                all_approved = all_approved and parsed["approved"]
                summaries.append(f"Chunk {index}: {parsed['summary']}")
                all_findings.extend(parsed["findings"])
                completed = datetime.now(timezone.utc)
                self.run_ledger.append_model_call(
                    role="independent_reviewer",
                    model=reviewer_model,
                    provider=str(getattr(self.client, "id", "")),
                    status="verified",
                    started_at=started.isoformat(),
                    completed_at=completed.isoformat(),
                    duration_ms=int((completed - started).total_seconds() * 1000),
                    detail=parsed["summary"][:1000],
                )
            except Exception as exc:
                all_approved = False
                failure = f"Review chunk {index} failed closed: {exc}"
                summaries.append(failure)
                all_findings.append(failure)
                completed = datetime.now(timezone.utc)
                self.run_ledger.append_model_call(
                    role="independent_reviewer",
                    model=reviewer_model,
                    provider=str(getattr(self.client, "id", "")),
                    status="failed",
                    started_at=started.isoformat(),
                    completed_at=completed.isoformat(),
                    duration_ms=int((completed - started).total_seconds() * 1000),
                    detail=_redact_runtime_text(str(exc)[:1000]),
                )

        summary = "\n".join(summaries)
        self.evidence.append(
            kind="independent_review",
            claim="independent hosted reviewer evaluated the applied diff",
            status="verified" if all_approved else "failed",
            raw_output=summary,
            metadata={
                "reviewer_model": reviewer_model,
                "chunks": len(chunks),
                "findings": all_findings,
            },
        )
        return all_approved, summary

    def _evaluate_unrelated_files(
        self, criterion: str, plan: Any, changes: list
    ) -> CriterionResult:
        permitted = list(getattr(plan, "permitted_files", []) or [])
        outside = []
        for item in changes:
            changed_path = Path(item["filepath"]).resolve()
            if not _is_relative_to(changed_path, Path(self.working_dir)):
                outside.append(item["filepath"])
                continue
            relative = changed_path.relative_to(Path(self.working_dir).resolve()).as_posix()
            if permitted and not any(
                fnmatch(relative, pattern) or relative == pattern for pattern in permitted
            ):
                outside.append(relative)
        return CriterionResult(
            criterion,
            CriterionStatus.UNSATISFIED if outside else CriterionStatus.SATISFIED,
            detail=(
                "Out-of-scope changes: " + ", ".join(outside)
                if outside
                else (
                    "All recorded changes matched the plan's permitted files."
                    if permitted
                    else "All recorded changes remained inside the authorized workspace."
                )
            ),
        )

    def _evaluate_fingerprinted_mutations(self, criterion: str, evidence: list) -> CriterionResult:
        mutation_records = [item for item in evidence if item.get("kind") == "file_mutation"]
        task_type = get_task_type(self._active_analysis.get("intent", IntentType.UNKNOWN))
        satisfied = (
            (not mutation_records and task_type == TaskType.READ_ONLY)
            or bool(mutation_records)
            and all(item.get("status") == "verified" for item in mutation_records)
        )
        return CriterionResult(
            criterion,
            CriterionStatus.SATISFIED if satisfied else CriterionStatus.UNVERIFIED,
            evidence_ids=[item["id"] for item in mutation_records],
            detail=(
                "Every recorded mutation passed disk verification."
                if satisfied
                else "No complete verified mutation set was recorded."
            ),
        )

    def _evaluate_objective_implementation(
        self,
        criterion: str,
        verified_mutations: list,
        passing_checks: list,
        passing_behavioral: list,
        approved_reviews: list,
        successful_command_text: set,
    ) -> CriterionResult:
        objective_evidence = [
            *verified_mutations,
            *passing_checks,
            *passing_behavioral,
            *approved_reviews,
        ]
        task_type = get_task_type(self._active_analysis.get("intent", IntentType.UNKNOWN))

        if task_type == TaskType.READ_ONLY:
            objective_satisfied = True
        elif task_type == TaskType.OPERATIONAL:
            objective_satisfied = bool(
                passing_checks or passing_behavioral or successful_command_text
            )
        else:
            objective_satisfied = (
                bool(verified_mutations)
                and bool(passing_checks or passing_behavioral)
                and bool(approved_reviews or self._is_nova_model())
            )

        return CriterionResult(
            criterion,
            CriterionStatus.SATISFIED if objective_satisfied else CriterionStatus.UNVERIFIED,
            evidence_ids=[item["id"] for item in objective_evidence],
            detail=(
                "Verified mutations, deterministic checks, and worker review "
                "support the requested objective."
                if objective_satisfied
                else "A mutation alone is insufficient; deterministic checks "
                "and review evidence are required."
            ),
        )

    def _evaluate_verification_checks(
        self, criterion: str, matched_checks: list
    ) -> CriterionResult:
        return CriterionResult(
            criterion,
            CriterionStatus.SATISFIED if matched_checks else CriterionStatus.UNVERIFIED,
            evidence_ids=[item["id"] for item in matched_checks],
            detail=(
                "A matching passing project check exists."
                if matched_checks
                else "No matching passing project check was recorded."
            ),
        )

    def _evaluate_security_constraints(
        self, criterion: str, passing_behavioral: list, matched_checks: list
    ) -> CriterionResult:
        security_evidence = [
            item for item in passing_behavioral if item.get("tool") == "security_scan"
        ] + matched_checks
        return CriterionResult(
            criterion,
            CriterionStatus.SATISFIED if security_evidence else CriterionStatus.UNVERIFIED,
            evidence_ids=[item["id"] for item in security_evidence],
            detail=(
                "A passing bounded security check was recorded."
                if security_evidence
                else "No passing security check was recorded."
            ),
        )

    def _finish_managed_run(
        self,
        content: str,
        events: list[dict[str, Any]] | None = None,
        *,
        status_override: RunStatus | None = None,
    ) -> dict[str, Any]:
        """Evaluate evidence and write a machine-readable final report."""
        if not self.run_ledger.turn_dir:
            return {}
        evidence = self.evidence.records()[getattr(self, "_turn_evidence_start", 0) :]
        mutation_records = self._effective_evidence(evidence, "file_mutation")
        verification_records = self._effective_evidence(evidence, "verification_check")
        effective_state_ids = {
            str(item.get("id")) for item in [*mutation_records, *verification_records]
        }
        changes = self.history.changes[self._run_history_start :]
        command_records = [item for item in evidence if item.get("kind") == "command"]
        passing_commands = [
            item
            for item in command_records
            if item.get("status") == "verified" and item.get("exit_code") == 0
        ]
        successful_command_text = {
            item.get("command", "") for item in passing_commands if item.get("command")
        }
        latest_behavioral_status = {
            item.get("tool", ""): item.get("status")
            for item in evidence
            if item.get("kind") == "behavioral_verification"
        }
        failed_evidence = [
            item
            for item in evidence
            if item.get("status") == "failed"
            and item.get("kind") not in {"routing", "independent_review"}
            and (
                item.get("kind") not in {"file_mutation", "verification_check"}
                or str(item.get("id")) in effective_state_ids
            )
            and not (
                item.get("kind") == "command" and item.get("command", "") in successful_command_text
            )
            and not (
                item.get("kind") == "behavioral_verification"
                and latest_behavioral_status.get(item.get("tool", "")) == "verified"
            )
        ]
        verified_mutations = [item for item in mutation_records if item.get("status") == "verified"]
        passing_behavioral = [
            item
            for item in evidence
            if item.get("kind") == "behavioral_verification" and item.get("status") == "verified"
        ]
        approved_reviews = [
            item
            for item in evidence
            if item.get("kind") == "independent_review" and item.get("status") == "verified"
        ]
        passing_checks = [item for item in verification_records if item.get("status") == "verified"]

        def matching_checks(criterion: str) -> list[dict[str, Any]]:
            lowered = criterion.lower()
            passing_by_type: dict[str, list[dict[str, Any]]] = {}
            for item in passing_checks:
                check_type = str(item.get("metadata", {}).get("check_type", ""))
                passing_by_type.setdefault(check_type, []).append(item)

            if "executable test" in lowered and "build" in lowered:
                target_types = {"test", "build", "browser", "api", "database"}
            elif "lint" in lowered and "type" in lowered:
                # A build is neither a linter nor a type checker. Combined
                # criteria require one passing record of each exact type.
                if not passing_by_type.get("lint") or not passing_by_type.get("type_check"):
                    return []
                return [*passing_by_type["lint"], *passing_by_type["type_check"]]
            elif "lint" in lowered:
                target_types = {"lint"}
            elif "type" in lowered:
                target_types = {"type_check"}
            elif "security" in lowered or "vulnerab" in lowered:
                target_types = {"security"}
            elif "coverage" in lowered:
                target_types = {"coverage"}
            elif "build" in lowered or "compile" in lowered:
                target_types = {"build"}
            elif "test" in lowered or "regression" in lowered:
                target_types = {"test"}
            elif "run the project" in lowered or "works" in lowered or "smoke" in lowered:
                target_types = {"test", "build", "browser", "api", "database"}
            else:
                return []
            return [
                item
                for item in passing_checks
                if item.get("metadata", {}).get("check_type") in target_types
            ]

        plan = self._active_plan
        if plan is not None:
            criteria_text = list(plan.acceptance_criteria)
            self.run_ledger.record_plan(plan)
        else:
            verification = self._applicable_verification(
                self._active_analysis.get("intent", IntentType.UNKNOWN),
                self._active_analysis.get("skills_needed", []),
            )
            criteria_text = self.planner._generate_acceptance_criteria(
                self._active_objective,
                self._active_analysis.get("intent", IntentType.UNKNOWN),
                verification,
            )

        results: list[CriterionResult] = []
        for criterion in criteria_text:
            lowered = criterion.lower()
            if "unrelated files" in lowered:
                results.append(self._evaluate_unrelated_files(criterion, plan, changes))
            elif "fingerprinted" in lowered:
                results.append(self._evaluate_fingerprinted_mutations(criterion, evidence))
            elif "requested objective is implemented" in lowered:
                results.append(
                    self._evaluate_objective_implementation(
                        criterion,
                        verified_mutations,
                        passing_checks,
                        passing_behavioral,
                        approved_reviews,
                        successful_command_text,
                    )
                )
            elif "security" in lowered or "vulnerab" in lowered:
                results.append(
                    self._evaluate_security_constraints(
                        criterion, passing_behavioral, matching_checks(criterion)
                    )
                )
            elif "verification completed" in lowered or any(
                term in lowered
                for term in ("test", "build", "lint", "type", "coverage", "smoke check")
            ):
                results.append(
                    self._evaluate_verification_checks(criterion, matching_checks(criterion))
                )
            elif failed_evidence:
                results.append(
                    CriterionResult(
                        criterion,
                        CriterionStatus.UNSATISFIED,
                        evidence_ids=[item["id"] for item in failed_evidence],
                        detail="One or more execution evidence records failed.",
                    )
                )
            else:
                results.append(
                    CriterionResult(
                        criterion,
                        CriterionStatus.UNVERIFIED,
                        detail="The run did not record sufficient deterministic evidence.",
                    )
                )

        # Autonomous execution is iterative: a failed command or edit attempt
        # is not an unresolved run failure when a later call to that tool
        # succeeds and final deterministic verification passes.
        latest_tool_events: dict[str, dict[str, Any]] = {}
        for item in events or []:
            if item.get("type") == "tool_call":
                latest_tool_events[str(item.get("name", "unknown"))] = item
        event_failures = [
            item for item in latest_tool_events.values() if not item.get("success", False)
        ]
        if status_override is not None:
            run_status = status_override
        elif (content or "").strip().upper().startswith("BLOCKED:"):
            run_status = RunStatus.BLOCKED
        elif self._pending_edits or self._pending_confirmations:
            run_status = RunStatus.AWAITING_APPROVAL
        elif failed_evidence or event_failures:
            run_status = (
                RunStatus.PARTIALLY_VERIFIED
                if verified_mutations or passing_checks
                else RunStatus.FAILED
            )
        elif results and all(item.status == CriterionStatus.SATISFIED for item in results):
            run_status = RunStatus.VERIFIED
        elif verified_mutations or passing_checks:
            run_status = RunStatus.PARTIALLY_VERIFIED
        else:
            run_status = RunStatus.UNVERIFIED

        checks = [
            {
                "evidence_id": item.get("id"),
                "command": item.get("command", ""),
                "status": item.get("status"),
                "exit_code": item.get("exit_code"),
            }
            for item in evidence
            if item.get("kind") == "command"
        ]
        risks = []
        if run_status != RunStatus.VERIFIED:
            risks.append("Not every acceptance criterion has passing deterministic evidence.")
        if self._pending_edits:
            risks.append(f"{len(self._pending_edits)} file edit(s) still require approval.")
        if self._pending_confirmations:
            risks.append(
                f"{len(self._pending_confirmations)} protected operation(s) still require approval."
            )

        if run_status == RunStatus.VERIFIED:
            outcome = "COMPLETED_VERIFIED"
        elif run_status == RunStatus.BLOCKED:
            outcome = "BLOCKED_BY_POLICY"
        elif run_status == RunStatus.AWAITING_APPROVAL:
            outcome = "AWAITING_APPROVAL"
        elif run_status == RunStatus.ROLLED_BACK:
            outcome = "ROLLED_BACK"
        elif run_status == RunStatus.FAILED:
            outcome = "FAILED"
        elif changes:
            outcome = "CHANGES_APPLIED_UNVERIFIED"
        elif run_status == RunStatus.PARTIALLY_VERIFIED:
            outcome = "COMPLETED_PARTIALLY_VERIFIED"
        else:
            outcome = "NO_CHANGES"

        turn_dir = self.run_ledger.turn_dir
        model_call_records, _model_call_corruption = self.run_ledger.read_jsonl("model_calls.jsonl")
        logical_model_calls = [
            item for item in model_call_records if item.get("role") != "provider_attempt"
        ]
        provider_attempt_records = [
            item for item in model_call_records if item.get("role") == "provider_attempt"
        ]

        def jsonl_count(filename: str) -> int:
            if turn_dir is None:
                return 0
            try:
                return sum(
                    1
                    for line in (turn_dir / filename).read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
            except OSError:
                return 0

        def event_kind_count(kind: str) -> int:
            if turn_dir is None:
                return 0
            try:
                records = [
                    json.loads(line)
                    for line in (turn_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            except (OSError, json.JSONDecodeError):
                return 0
            return sum(item.get("kind") == kind for item in records)

        report = self.run_ledger.finalize(
            run_status,
            objective=self._active_objective,
            outcome=outcome,
            criteria=results,
            files_changed=[item["filepath"] for item in changes],
            checks=checks,
            costs=self.budget.snapshot(),
            risks=risks,
            work_completed=[f"Updated {Path(item['filepath']).name}" for item in changes],
            checks_skipped=[
                item.criterion
                for item in results
                if item.status
                in {
                    CriterionStatus.SKIPPED,
                    CriterionStatus.BLOCKED,
                    CriterionStatus.UNVERIFIED,
                }
            ],
            dependencies_added=sorted(
                {
                    (
                        f"{item.get('metadata', {}).get('registry', 'registry')}:"
                        f"{item.get('metadata', {}).get('name', 'unknown')}"
                    )
                    for item in evidence
                    if item.get("kind") == "package_registry"
                    and item.get("status") in {"pass", "warn"}
                }
            ),
            permissions_used=sorted(self._permissions_used),
            network_calls=list(dict.fromkeys(self._network_calls)),
            model_providers=list(
                dict.fromkeys(
                    [
                        self.model_key,
                        *(
                            [self.model_cfg.get("intern_model", "nova_codex")]
                            if self.routing_stats["nova_tasks"]
                            else []
                        ),
                    ]
                )
            ),
            assumptions=[],
            metadata={
                "model": self.model_key,
                "response_excerpt": _redact_runtime_text((content or "")[:2000]),
                "evidence_path": str(self.evidence.path),
                "workspace": self.working_dir,
                "history_start": self._run_history_start,
                "history_end": len(self.history.changes),
                "local_intern_mode": self.local_intern_mode,
                "local_intern_enabled": self.local_intern_enabled,
                "plugins_enabled": self._plugins_enabled,
                "model_calls": len(logical_model_calls),
                "provider_attempts": len(provider_attempt_records),
                "tool_calls": jsonl_count("tool_calls.jsonl"),
                "tests_executed": len(verification_records),
                "criteria_satisfied": sum(
                    item.status == CriterionStatus.SATISFIED for item in results
                ),
                "criteria_unverified": sum(
                    item.status == CriterionStatus.UNVERIFIED for item in results
                ),
                "rollbacks": event_kind_count("rollback"),
            },
        )
        return report

    def get_run_status(self) -> str:
        """Return the latest durable run and workspace status."""
        summary = self.run_ledger.resume_summary()
        if not summary:
            return "No durable run exists for this session."
        state = summary.get("state", {})
        report = summary.get("final_report", {})
        lines = [
            f"Run: {state.get('turn_id', 'unknown')}",
            f"Status: {report.get('status') or state.get('status', 'unknown')}",
            f"Objective: {report.get('objective') or summary.get('request', {}).get('request', '')}",
            f"Run directory: {self.run_ledger._latest_turn_dir()}",
        ]
        if self.worktree:
            worktree_status = self.worktree.status()
            lines.extend(
                [
                    f"Worktree: {worktree_status.get('path', self.working_dir)}",
                    f"Branch: {worktree_status.get('branch', '')}",
                    worktree_status.get("git_status", ""),
                ]
            )
        checkpoint = summary.get("checkpoint", {})
        if checkpoint:
            lines.append(
                f"Latest checkpoint: {checkpoint.get('checkpoint')} {checkpoint.get('label', '')}"
            )
        return "\n".join(item for item in lines if item)

    def rollback_current_run(self) -> tuple[bool, str]:
        """Atomically roll back every file operation recorded by this run."""
        change_count = len(self.history.changes) - self._run_history_start
        if change_count <= 0:
            return False, "The current run has no applied file changes to roll back."
        success, detail = self.history.undo_changes(change_count)
        if success:
            self.run_ledger.mark_rolled_back(detail)
            try:
                self.repo_graph.build()
            except Exception:
                pass
        return success, detail

    def _refresh_final_report_after_approval(self) -> None:
        """Recompute the final status after an approval queue changes."""
        if not self.run_ledger.turn_dir or not self._active_objective:
            return
        prior = self.run_ledger.resume_summary().get("final_report", {})
        content = prior.get("metadata", {}).get("response_excerpt", "")
        self._finish_managed_run(content, [])

    # ── Message Building ─────────────────────────────────────────────────

    def _gather_context(self) -> str:
        """Auto-gather project context on first interaction."""
        if self._context_gathered:
            return ""
        self._context_gathered = True

        # Use the new ContextManager for initialization
        try:
            context = self.context_mgr.initialize()
            stats = self.repo_graph.build()
            graph = self.repo_graph.summary()
            graph_context = (
                "[REPOSITORY GRAPH]\n"
                f"files={graph['files']} symbols={graph['symbols']} "
                f"imports={graph['imports']} tests={graph['tests']} "
                f"parse_errors={graph['parse_errors']} "
                f"incremental_reused={stats.reused}"
            )
            return context + graph_context + "\n\n---\n\n"
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
            "package.json",
            "pyproject.toml",
            "Cargo.toml",
            "go.mod",
            "Makefile",
            "Dockerfile",
            "docker-compose.yml",
            "tsconfig.json",
            ".eslintrc.json",
            "requirements.txt",
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
                + cwd_info
                + time_info
                + os_info
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

        for extension_tool in self.extensions.loaded("tools"):
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": extension_tool.name,
                        "description": extension_tool.description,
                        "parameters": extension_tool.input_schema,
                    },
                }
            )

        # MCP tools
        try:
            tools.extend(self.mcp.get_all_tool_definitions())
        except Exception:
            pass

        configured_allowlist = set(self.allowed_tools)
        step_allowlist: set[str] = set()
        if self._active_plan is not None:
            current = next(
                (step for step in self._active_plan.steps if step.status == TaskStatus.IN_PROGRESS),
                None,
            )
            if current:
                step_allowlist.update(current.tools_needed)
                step_allowlist.update(
                    {
                        "read_file",
                        "search_code",
                        "list_directory",
                        "find_files",
                        "get_project_structure",
                        "repo_context",
                        "repo_symbols",
                        "repo_impact",
                    }
                )
        effective_allowlist = (
            configured_allowlist & step_allowlist
            if configured_allowlist and step_allowlist
            else configured_allowlist or step_allowlist
        )

        def permitted(definition: dict[str, Any]) -> bool:
            name = str(definition.get("function", {}).get("name", ""))
            return bool(
                name
                and name not in self.disallowed_tools
                and (not effective_allowlist or name in effective_allowlist)
            )

        return [definition for definition in tools if permitted(definition)]

    def close(self, *, discard_workspace: bool = False) -> dict[str, Any]:
        """Release transports and optionally archive/discard the isolated workspace."""

        report: dict[str, Any] = {
            "mcp_disconnected": False,
            "background_processes_stopped": [],
            "workspace_discarded": False,
            "recovery_patch": "",
            "errors": [],
        }
        try:
            self.mcp.disconnect_all()
            report["mcp_disconnected"] = True
        except Exception as exc:
            report["errors"].append(f"MCP cleanup failed: {exc}")
        try:
            from nexus.tools import stop_owned_processes

            process_cleanup = stop_owned_processes(self.conversation_id)
            report["background_processes_stopped"] = process_cleanup["stopped"]
            report["errors"].extend(process_cleanup["errors"])
        except Exception as exc:
            report["errors"].append(f"Background process cleanup failed: {exc}")
        if discard_workspace and self.worktree is not None and self.worktree.info is not None:
            try:
                diff = self.worktree.diff()
                if diff:
                    if self.run_ledger.turn_dir:
                        patch = self.run_ledger.store_artifact(
                            "patches", "workspace-close-recovery.diff", diff
                        )
                    else:
                        recovery_dir = nexus_home() / "recovery"
                        recovery_dir.mkdir(parents=True, exist_ok=True)
                        patch = recovery_dir / f"{self.conversation_id}-workspace.diff"
                        patch.write_text(diff, encoding="utf-8")
                    report["recovery_patch"] = str(patch)
                cleanup = self.worktree.discard()
                report["workspace_discarded"] = not cleanup["errors"]
                report["errors"].extend(cleanup["errors"])
            except Exception as exc:
                report["errors"].append(f"Workspace cleanup failed: {exc}")
        return report

    # ── Tool Execution (with safety, hooks, reflection) ──────────────────

    def _execute_tool_with_safety(
        self,
        name: str,
        args: dict,
        *,
        _user_confirmed: bool = False,
        _edit_confirmed: bool = False,
    ) -> tuple[str, bool]:
        """Execute a guarded tool and mirror its outcome into the run ledger."""
        started = time.monotonic()
        from nexus.tools import tool_context

        with tool_context(self.working_dir, self.history, self.conversation_id):
            result, success = self._execute_tool_with_safety_impl(
                name,
                args,
                _user_confirmed=_user_confirmed,
                _edit_confirmed=_edit_confirmed,
            )
        if _user_confirmed:
            self._permissions_used.add(f"{name}: explicit approval")
        if success and name in {"web_fetch", "web_search", "api_check", "browser_check"}:
            target = str(args.get("url") or args.get("query") or "")
            self._network_calls.append(f"{name}: {target}")
        elif success and args.get("network"):
            target = str(args.get("command") or args.get("argv") or name)
            self._network_calls.append(f"{name}: {target}")
        if self.run_ledger.turn_dir:
            safe_args = {
                key: _redact_runtime_text(value) if isinstance(value, str) else value
                for key, value in args.items()
                if key
                not in {
                    "content",
                    "old_text",
                    "new_text",
                    "new_content",
                    "_nova_guardrail",
                }
            }
            self.run_ledger.append_event(
                "tool_call",
                status="verified" if success else "failed",
                detail=(
                    f"{name} completed successfully."
                    if success
                    else _redact_runtime_text((result or "")[:1000])
                ),
                metadata={
                    "tool": name,
                    "arguments": safe_args,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
            )
            evidence_records = self.evidence.records(limit=1)
            self.run_ledger.append_tool_call(
                tool=name,
                status="verified" if success else "failed",
                arguments=safe_args,
                evidence_id=(evidence_records[-1].get("id", "") if evidence_records else ""),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            self.run_ledger.record_costs(self.budget.snapshot())
            mutation_tools = {"write_file", "edit_file", "patch_file", "multi_edit"}
            if success and name in mutation_tools:
                raw_paths = (
                    [item.get("path", "") for item in args.get("edits", [])]
                    if name == "multi_edit"
                    else [args.get("path", "")]
                )
                try:
                    self.repo_graph.update_paths(path for path in raw_paths if path)
                except Exception:
                    pass
                self.run_ledger.checkpoint(
                    f"verified-{name}",
                    plan=self._active_plan,
                    evidence_count=len(self.evidence.records()),
                    history_count=len(self.history.changes),
                    metadata={"paths": [path for path in raw_paths if path]},
                )
            elif success and name in ("run_command", "run_process"):
                self.run_ledger.checkpoint(
                    "command-completed",
                    plan=self._active_plan,
                    evidence_count=len(self.evidence.records()),
                    history_count=len(self.history.changes),
                    metadata={"command": _redact_runtime_text(str(args.get("command", ""))[:500])},
                )
        return result, success

    def _enforce_tool_policy(
        self,
        name: str,
        args: dict,
        command: str,
        scope_paths: list[str],
        pending_args: dict,
        _user_confirmed: bool,
        _edit_confirmed: bool,
        mutation_tools: tuple,
        read_tools: set,
    ) -> tuple[bool, str, tuple[str, bool]]:
        if name in self.disallowed_tools:
            return (
                False,
                "",
                (f"❌ BLOCKED: {name} is denied by the active permission rules.", False),
            )
        if self.allowed_tools and name not in self.allowed_tools:
            return False, "", (f"❌ BLOCKED: {name} is not in the active tool allowlist.", False)
        if self._active_plan is not None and self._enforce_plan_tool_contract:
            current = next(
                (step for step in self._active_plan.steps if step.status == TaskStatus.IN_PROGRESS),
                None,
            )
            if current is not None:
                step_tools = set(current.tools_needed) | {
                    "read_file",
                    "search_code",
                    "list_directory",
                    "find_files",
                    "get_project_structure",
                    "repo_context",
                    "repo_symbols",
                    "repo_impact",
                }
                if name not in step_tools:
                    return (
                        False,
                        "",
                        (
                            f"❌ BLOCKED: {name} is outside the active plan step's tool contract.",
                            False,
                        ),
                    )
        if not self.mode_policy.may_edit and (
            name in mutation_tools
            or name in ("run_command", "run_process", "process_run")
            or name.startswith("git_")
        ):
            return (
                False,
                "",
                (
                    "❌ BLOCKED: Current mode is read-only. Switch mode before executing changes.",
                    False,
                ),
            )

        policy_capability = ""
        policy_targets: list[str] = []
        if name in mutation_tools:
            policy_capability = "write"
            policy_targets = scope_paths
        elif name in ("run_command", "run_process", "process_run"):
            normalized_command = command.lower()
            if re.search(r"\bgit\s+push\b", normalized_command):
                policy_capability = "git_push"
            elif re.search(
                r"\b(?:pip|pip3|uv)\s+(?:pip\s+)?install\b"
                r"|\b(?:npm|pnpm|yarn)\s+(?:add|install)\b"
                r"|\bcargo\s+add\b|\bgo\s+get\b",
                normalized_command,
            ):
                policy_capability = "package_install"
            elif re.search(
                r"\b(?:kubectl\s+(?:apply|delete)|helm\s+(?:install|upgrade)|"
                r"terraform\s+apply|vercel\s+deploy)\b",
                normalized_command,
            ):
                policy_capability = "deployment"
            else:
                policy_capability = "command"
            policy_targets = [command]
        elif name.startswith("git_"):
            policy_capability = "command"
            policy_targets = [name]
        elif name in read_tools:
            policy_capability = "read"
            policy_targets = scope_paths or [name]
        elif name in ("web_fetch", "web_search", "api_check", "browser_check"):
            policy_capability = "network_access"
            policy_targets = [str(args.get("url") or args.get("query") or "")]

        if policy_capability:
            approval_targets = []
            for policy_target in policy_targets or [name]:
                policy_decision = self.policy.decide(
                    policy_capability,
                    policy_target,
                )
                extension_asked = False
                for provider in self.extensions.loaded("policies"):
                    external = str(
                        provider.decide(
                            policy_capability,
                            policy_target,
                            ToolContext(
                                working_dir=self.working_dir,
                                session_id=self.conversation_id,
                                permission_mode=self.permission_mode,
                            ),
                        )
                    ).lower()
                    if external == PermissionDecision.DENY.value:
                        policy_decision = PermissionDecision.DENY
                        break
                    if external == PermissionDecision.ASK.value:
                        policy_decision = PermissionDecision.ASK
                        extension_asked = True
                if policy_decision == PermissionDecision.DENY:
                    return (
                        False,
                        "",
                        (
                            f"❌ BLOCKED: repository policy denies {policy_capability} "
                            f"for {policy_target or name}.",
                            False,
                        ),
                    )
                if policy_decision == PermissionDecision.ASK and (
                    self.policy.source or extension_asked
                ):
                    approval_targets.append(policy_target or name)
            policy_requires_approval = approval_targets and not _user_confirmed
            if policy_requires_approval:
                policy_target = ", ".join(approval_targets)
                policy_check = SafetyCheck(
                    level=SafetyLevel.DANGEROUS,
                    operation=f"{policy_capability}: {policy_target or name}",
                    reason=f"Repository policy requires approval for {policy_capability}",
                    details=policy_target or name,
                    requires_confirmation=True,
                )
                confirmation_id = self._queue_confirmation(
                    name=name,
                    args=pending_args,
                    safety_check=policy_check,
                    edit_confirmed=_edit_confirmed,
                )
                return (
                    False,
                    "",
                    (
                        "⏸️ PENDING_CONFIRMATION "
                        f"[{confirmation_id}]: {policy_check.reason}. "
                        f"Enter /confirm {confirmation_id} or /cancel {confirmation_id}.",
                        False,
                    ),
                )
        return True, policy_capability, ("", False)

    def _enforce_network_safety(
        self,
        name: str,
        args: dict,
        command: str,
        pending_args: dict,
        _user_confirmed: bool,
        _edit_confirmed: bool,
    ) -> tuple[bool, tuple[str, bool]]:
        requests_network = bool(args.get("network")) or bool(args.get("allow_external"))
        if requests_network and not _user_confirmed:
            network_check = SafetyCheck(
                level=SafetyLevel.DANGEROUS,
                operation=f"{name} network access",
                reason="Network access is disabled by default",
                details=command or str(args.get("url", "")),
                requires_confirmation=True,
            )
            confirmation_id = self._queue_confirmation(
                name=name,
                args=pending_args,
                safety_check=network_check,
                edit_confirmed=_edit_confirmed,
            )
            return False, (
                "⏸️ PENDING_CONFIRMATION "
                f"[{confirmation_id}]: {network_check.reason}. "
                f"Enter /confirm {confirmation_id} or /cancel {confirmation_id}.",
                False,
            )
        return True, ("", False)

    def _enforce_package_safety(
        self,
        name: str,
        args: dict,
        command: str,
        pending_args: dict,
        _user_confirmed: bool,
        _edit_confirmed: bool,
        mutation_tools: tuple,
    ) -> tuple[bool, str, tuple[str, bool]]:
        package_checks = []
        package_warning_text = ""
        if name in mutation_tools:
            for package_path, proposed_content in self._dependency_candidates(name, args):
                package_checks.extend(
                    self.package_guard.check_file_change(package_path, proposed_content)
                )
        elif name in ("run_command", "run_process", "process_run") and command:
            package_checks = self.package_guard.check_command(command)
        if package_checks:
            for check in package_checks:
                self.evidence.append(
                    kind="package_registry",
                    claim=f"registry check for {check.registry}:{check.name}",
                    status=check.status,
                    tool=name,
                    raw_output=check.reason,
                    metadata={
                        "registry": check.registry,
                        "name": check.name,
                        "registry_url": check.url,
                    },
                )
            blocked = [check for check in package_checks if check.blocked]
            if blocked:
                details = "\n".join(
                    f"  {check.registry}:{check.name} — {check.reason}" for check in blocked
                )
                return False, "", (f"❌ BLOCKED by anti-slopsquatting guard:\n{details}", False)
            unverified = [check for check in package_checks if check.requires_confirmation]
            if unverified and not _user_confirmed:
                details = "\n".join(
                    f"  {check.registry}:{check.name} — {check.reason}" for check in unverified
                )
                uncertainty_check = SafetyCheck(
                    level=SafetyLevel.DANGEROUS,
                    operation=f"{name} with unverified package metadata",
                    reason=(
                        "The package registry could not be verified. This is not "
                        "treated as proof of a malicious package, but continuing "
                        "requires explicit approval"
                    ),
                    details=details,
                    requires_confirmation=True,
                )
                confirmation_id = self._queue_confirmation(
                    name=name,
                    args=pending_args,
                    safety_check=uncertainty_check,
                    edit_confirmed=_edit_confirmed,
                )
                return (
                    False,
                    "",
                    (
                        "⏸️ PENDING_CONFIRMATION "
                        f"[{confirmation_id}]: {uncertainty_check.reason}. "
                        "This operation was not executed. Review the exact operation, then "
                        f"enter /confirm {confirmation_id} or /cancel {confirmation_id}.\n"
                        f"{details}",
                        False,
                    ),
                )
            warnings = [check for check in package_checks if check.status == "warn"]
            if warnings:
                package_warning_text = "⚠️ PACKAGE RISK WARNING:\n" + "\n".join(
                    f"  {check.registry}:{check.name} — {check.reason}" for check in warnings
                )
        return True, package_warning_text, ("", False)

    def _prepare_mutation_diff(
        self,
        name: str,
        args: dict,
        pending_args: dict,
        _user_confirmed: bool,
        _edit_confirmed: bool,
        mutation_tools: tuple,
    ) -> tuple[bool, str, tuple[str, bool]]:
        mutation_diff = ""
        if name in mutation_tools:
            ok, mutation_diff = preview_mutation(name, args, self.working_dir)
            if not ok:
                return False, "", (f"❌ Cannot create a safe diff preview: {mutation_diff}", False)
            if self.mode_policy.require_review and not _edit_confirmed:
                confirmation_id = self._queue_edit(name, pending_args, mutation_diff)
                return (
                    False,
                    "",
                    (
                        "⏸️ PENDING_EDIT_CONFIRMATION "
                        f"[{confirmation_id}]: The file edit has been queued for review.\n"
                        f"Enter `/apply {confirmation_id}` or `/reject {confirmation_id}`.\n"
                        f"Diff preview:\n```diff\n{mutation_diff}\n```",
                        False,
                    ),
                )
        return True, mutation_diff, ("", False)

    def _dispatch_tool_execution(
        self,
        name: str,
        args: dict,
    ) -> str:
        # Check plugin tool dispatch first
        for plugin in self.plugin_loader.plugins.values():
            dispatch = plugin.get_tool_dispatch()
            if name in dispatch:
                try:
                    return dispatch[name](**args)
                except Exception as e:
                    return f"❌ Plugin tool error: {e}"

        for extension_tool in self.extensions.loaded("tools"):
            if extension_tool.name != name:
                continue
            try:
                extension_result = extension_tool.invoke(
                    args,
                    ToolContext(
                        working_dir=self.working_dir,
                        session_id=self.conversation_id,
                        task_id=(
                            str(self._active_plan.current_step)
                            if self._active_plan is not None
                            else ""
                        ),
                        permission_mode=self.permission_mode,
                    ),
                )
                return (
                    extension_result
                    if isinstance(extension_result, str)
                    else json.dumps(extension_result, ensure_ascii=False)
                )
            except Exception as exc:
                return f"❌ Extension tool error: {exc}"

        if self.mcp.is_mcp_tool(name):
            return self.mcp.call_tool(name, args)
        else:
            return execute_tool(name, args)

    def _execute_tool_with_safety_impl(
        self,
        name: str,
        args: dict,
        *,
        _user_confirmed: bool = False,
        _edit_confirmed: bool = False,
    ) -> tuple[str, bool]:
        """
        Execute a tool with full safety checks, hooks, and context tracking.

        Pipeline: Before Hooks → Safety Check → Execute → Context Track → After Hooks → Reflection
        """
        from nexus.tools import normalize_tool_arguments

        args = normalize_tool_arguments(name, args)
        pending_args = dict(args)
        nova_guardrail = args.pop("_nova_guardrail", None)
        file_path = args.get("path", "") or args.get("file_path", "")
        command = args.get("command", "")
        if name == "run_process":
            raw_argv = args.get("argv", [])
            command = shlex.join(str(item) for item in raw_argv) if raw_argv else ""
        if (
            name in {"run_command", "run_process", "process_run"}
            and re.search(
                r"\b(?:curl|wget|ssh|scp|sftp|ftp|rsync|gh)\b"
                r"|\bgit\s+(?:clone|fetch|pull|push)\b"
                r"|\b(?:pip|pip3|uv)\s+(?:pip\s+)?install\b"
                r"|\b(?:npm|pnpm|yarn)\s+(?:add|install|publish)\b"
                r"|\b(?:docker|podman)\s+(?:pull|push)\b"
                r"|\bcargo\s+(?:add|install)\b|\bgo\s+get\b",
                command.lower(),
            )
            or name == "github_create_pr"
        ):
            args["network"] = True
            pending_args["network"] = True
        mutation_tools = ("write_file", "edit_file", "patch_file", "multi_edit")
        read_tools = {
            "read_file",
            "file_info",
            "diff_files",
            "search_code",
            "list_directory",
            "find_files",
            "get_project_structure",
            "repo_index",
            "repo_symbols",
            "repo_impact",
            "repo_context",
            "repo_routes",
            "repo_models",
            "repo_navigate",
            "database_check",
            "security_scan",
        }

        scope_paths = []
        if name == "multi_edit":
            scope_paths.extend(str(item.get("path", "")) for item in args.get("edits", []))
        elif file_path:
            scope_paths.append(str(file_path))
        if name == "diff_files":
            scope_paths.extend(str(args.get(key, "")) for key in ("file_a", "file_b"))
        elif name in {"search_code", "find_files"}:
            scope_paths.append(str(args.get("directory", "")))
        elif name in {"run_command", "run_process", "process_run"}:
            scope_paths.append(str(args.get("cwd", "")))
        elif name == "repo_impact":
            scope_paths.extend(str(item) for item in args.get("paths", []))
        elif name == "security_scan":
            scope_paths.extend(str(item) for item in args.get("paths", []) or [])
        elif name == "browser_check":
            scope_paths.append(str(args.get("screenshot_path", "")))
        scope_paths = list(dict.fromkeys(item for item in scope_paths if item))

        # ── 1. Enforce Tool Policy
        ok, policy_capability, err_res = self._enforce_tool_policy(
            name,
            args,
            command,
            scope_paths,
            pending_args,
            _user_confirmed,
            _edit_confirmed,
            mutation_tools,
            read_tools,
        )
        if not ok:
            return err_res

        # ── 2. Enforce Network Safety
        ok, err_res = self._enforce_network_safety(
            name, args, command, pending_args, _user_confirmed, _edit_confirmed
        )
        if not ok:
            return err_res

        # Nova Guardrail checks for mutations
        if name in mutation_tools:
            if nova_guardrail is not None and not nova_guardrail.get("passed"):
                return "❌ BLOCKED: Nova guardrail metadata was present but did not pass.", False
            if self._is_nova_model() and (not nova_guardrail or not nova_guardrail.get("passed")):
                return (
                    "❌ BLOCKED: Nova file edit reached Nexus without a passing Nova "
                    "guardrail verdict (path validation, constraint verification, and disk gate).",
                    False,
                )
            early_edits = args.get("edits", []) if name == "multi_edit" else [args]
            for early_edit in early_edits:
                early_path = early_edit.get("path", "")
                early_content = (
                    early_edit.get("content", "")
                    or early_edit.get("new_text", "")
                    or early_edit.get("new_content", "")
                )
                early_check = self.safety.check_file_write(early_path, early_content)
                if early_check.level == SafetyLevel.BLOCKED:
                    return f"❌ BLOCKED: {early_check.reason}", False

        # Resolve scope outside workspace
        for scoped_path in (item for item in scope_paths if item):
            resolved_file = Path(scoped_path).expanduser()
            if not resolved_file.is_absolute():
                resolved_file = Path(self.working_dir) / resolved_file
            resolved_file = resolved_file.resolve()
            roots = [Path(self.working_dir), *(Path(item) for item in self.additional_dirs)]
            if any(_is_relative_to(resolved_file, root) for root in roots):
                continue
            if not _user_confirmed:
                scope_check = SafetyCheck(
                    level=SafetyLevel.DANGEROUS,
                    operation=f"{name} outside workspace",
                    reason="File access is outside the current workspace",
                    details=str(resolved_file),
                    requires_confirmation=True,
                )
                confirmation_id = self._queue_confirmation(
                    name=name,
                    args=pending_args,
                    safety_check=scope_check,
                    edit_confirmed=_edit_confirmed,
                )
                return (
                    "⏸️ PENDING_CONFIRMATION "
                    f"[{confirmation_id}]: {scope_check.reason}. "
                    "This operation was not executed. Review the exact operation, then "
                    f"enter /confirm {confirmation_id} or /cancel {confirmation_id}.\n"
                    f"{scope_check.details}",
                    False,
                )

        # ── 3. Enforce Package Safety
        ok, package_warning_text, err_res = self._enforce_package_safety(
            name, args, command, pending_args, _user_confirmed, _edit_confirmed, mutation_tools
        )
        if not ok:
            return err_res

        # ── 4. File diff approval gate
        ok, mutation_diff, err_res = self._prepare_mutation_diff(
            name, args, pending_args, _user_confirmed, _edit_confirmed, mutation_tools
        )
        if not ok:
            return err_res

        # ── Fire BEFORE hooks
        event_before = None
        event_after = None

        if name in ("write_file",):
            event_before = HookEvent.BEFORE_FILE_CREATE
            event_after = HookEvent.AFTER_FILE_CREATE
        elif name in ("edit_file", "patch_file", "multi_edit"):
            event_before = HookEvent.BEFORE_FILE_EDIT
            event_after = HookEvent.AFTER_FILE_EDIT
        elif name in ("run_command", "run_process", "process_run"):
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

        if event_before:
            hook_ctx.event = event_before
            hook_results = self.hooks.fire(event_before, hook_ctx)
            if any(r.blocked for r in hook_results):
                return "❌ Operation blocked by hook policy.", False

        # ── Safety check ──
        safety_check = None
        if name in ("run_command", "run_process", "process_run") and command:
            safety_check = self.safety.check_command(command)
        elif name == "multi_edit":
            for edit in args.get("edits", []):
                check = self.safety.check_file_write(edit.get("path", ""), edit.get("new_text", ""))
                if check.level in (SafetyLevel.BLOCKED, SafetyLevel.DANGEROUS):
                    safety_check = check
                    break
        elif name in mutation_tools and file_path:
            content_val = (
                args.get("content", "") or args.get("new_text", "") or args.get("new_content", "")
            )
            safety_check = self.safety.check_file_write(file_path, content_val)

        if safety_check and safety_check.level == SafetyLevel.BLOCKED:
            return f"❌ BLOCKED: {safety_check.reason}", False
        elif safety_check and safety_check.level == SafetyLevel.DANGEROUS and not _user_confirmed:
            confirmation_id = self._queue_confirmation(
                name=name,
                args=pending_args,
                safety_check=safety_check,
                edit_confirmed=_edit_confirmed,
            )
            return (
                "⏸️ PENDING_CONFIRMATION "
                f"[{confirmation_id}]: {safety_check.reason}. "
                "This operation was not executed. Review the exact operation, then "
                f"enter /confirm {confirmation_id} or /cancel {confirmation_id}.\n"
                f"{safety_check.details}",
                False,
            )

        # Autonomous production presets never execute a dangerous or networked
        # command through the policy-only restricted subprocess fallback. Safe,
        # local verification commands remain portable on hosts without bwrap or
        # sandbox-exec; elevated operations fail closed unless native isolation
        # is actually available.
        if (
            name in ("run_command", "run_process", "process_run")
            and self.mode_policy.require_os_isolation
            and (
                bool(args.get("network"))
                or bool(safety_check and safety_check.level == SafetyLevel.DANGEROUS)
            )
        ):
            args["require_os_isolation"] = True

        # ── 5. Execute
        result = self._dispatch_tool_execution(name, args)

        success = not result.startswith(("❌", "⏰", "⏸️"))
        if name in ("api_check", "database_check", "browser_check", "security_scan"):
            try:
                success = json.loads(result).get("status") == "passed"
            except (AttributeError, TypeError, json.JSONDecodeError):
                success = False

        if package_warning_text:
            result = package_warning_text + "\n" + result

        # ── Verified-completion evidence
        if success and name in mutation_tools:
            verified, detail, artifacts = verify_mutation(name, args, self.working_dir)
            code_checks = []
            code_failures = []
            if verified:
                candidate_actions = []
                raw_paths = (
                    [edit.get("path", "") for edit in args.get("edits", [])]
                    if name == "multi_edit"
                    else [args.get("path", "")]
                )
                for raw_path in raw_paths:
                    try:
                        target = Path(raw_path).expanduser()
                        if not target.is_absolute():
                            target = Path(self.working_dir) / target
                        relative = target.resolve().relative_to(Path(self.working_dir))
                        candidate_actions.append(SimpleNamespace(path=str(relative)))
                    except ValueError:
                        continue
                code_checks = GeneratedCodeValidator(self.working_dir).validate(candidate_actions)
                code_failures = [check for check in code_checks if not check.passed]
                if code_failures:
                    verified = False
                    detail = "compiler validation failed: " + " | ".join(
                        check.format() for check in code_failures
                    )
                    undo_count = len(args.get("edits", [])) if name == "multi_edit" else 1
                    rollback_ok, rollback_output = self.history.undo_changes(max(1, undo_count))
                    detail += (
                        f" | rollback={'succeeded' if rollback_ok else 'failed'}: {rollback_output}"
                    )
            if code_checks:
                self.evidence.append(
                    kind="verification_check",
                    claim="generated code compiler and syntax validation",
                    status="verified" if not code_failures else "failed",
                    tool="generated_code_validator",
                    command="generated-code-validator",
                    exit_code=0 if not code_failures else 1,
                    raw_output="\n".join(check.format() for check in code_checks),
                    metadata={"check_type": "syntax"},
                )
            self.evidence.append(
                kind="file_mutation",
                claim=f"{name} persisted the requested change",
                status="verified" if verified else "failed",
                tool=name,
                artifacts=artifacts,
                raw_output=result,
                metadata={"verification": detail},
            )
            if not verified:
                return f"❌ WRITE VERIFICATION FAILED: {detail}\nRaw tool output:\n{result}", False
            if self.run_ledger.turn_dir and mutation_diff:
                self.run_ledger.store_artifact(
                    "patches",
                    f"{name}-{len(self.history.changes):04d}.diff",
                    mutation_diff,
                )
            result += f"\n🔎 VERIFIED: {detail}\nEvidence: {self.evidence.path}"
        elif name in ("run_command", "run_process", "process_run"):
            exit_code = (
                command_exit_code(result) if name in ("run_command", "run_process") else None
            )
            status = (
                "verified" if success and (exit_code == 0 or name == "process_run") else "failed"
            )
            self.evidence.append(
                kind="command",
                claim=f"executed command: {command}",
                status=status,
                tool=name,
                command=command,
                exit_code=exit_code,
                raw_output=result,
            )
        elif name in ("api_check", "database_check", "browser_check", "security_scan"):
            probe_status = ""
            try:
                probe_status = str(json.loads(result).get("status", ""))
            except (TypeError, json.JSONDecodeError):
                pass
            self.evidence.append(
                kind="behavioral_verification",
                claim=f"executed {name}",
                status="verified" if success and probe_status == "passed" else "failed",
                tool=name,
                raw_output=result,
                metadata={"probe_status": probe_status},
            )
        elif name.startswith("git_"):
            self.evidence.append(
                kind="git_operation",
                claim=f"executed {name}",
                status="verified" if success else "failed",
                tool=name,
                raw_output=result,
                metadata={"arguments": args},
            )

        # ── 6. Track file access in context manager
        if file_path:
            was_edited = name in ("write_file", "edit_file", "patch_file", "multi_edit")
            self.context_mgr.track_file_access(file_path, was_edited=was_edited)
            if success and name == "read_file" and result:
                self.context_mgr.track_file_imports(file_path, result)
                self.context_mgr.summarize_file(file_path, result)

        # ── 7. Fire AFTER hooks
        if event_after:
            hook_ctx.event = event_after
            hook_ctx.tool_result = result
            self.hooks.fire(event_after, hook_ctx)

        # ── 8. Fire error hook on failure
        if not success:
            self.hooks.fire(
                HookEvent.ON_ERROR,
                HookContext(
                    event=HookEvent.ON_ERROR,
                    error_message=result[:500],
                    tool_name=name,
                    tool_args=args,
                ),
            )

        return result, success

    def _dependency_candidates(self, name: str, args: dict) -> list[tuple[str, str]]:
        """Build the exact proposed dependency-file content without writing it."""
        candidates: list[tuple[str, str]] = []
        edits = args.get("edits", []) if name == "multi_edit" else [args]
        edit_name = "edit_file" if name == "multi_edit" else name
        for edit in edits:
            raw_path = edit.get("path", "")
            if Path(raw_path).name not in {
                "requirements.txt",
                "requirements-dev.txt",
                "package.json",
                "Cargo.toml",
                "go.mod",
            }:
                continue
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = Path(self.working_dir) / path
            try:
                old = path.read_text(encoding="utf-8") if path.exists() else ""
            except OSError:
                old = ""
            if edit_name == "write_file":
                new = str(edit.get("content", ""))
            elif edit_name == "edit_file":
                new = old.replace(str(edit.get("old_text", "")), str(edit.get("new_text", "")), 1)
            elif edit_name == "patch_file":
                lines = old.splitlines()
                start, end = int(edit.get("start_line", 1)), int(edit.get("end_line", 0))
                replacement = str(edit.get("new_content", "")).splitlines()
                lines[start - 1 : (start - 1 if end == 0 else end)] = replacement
                new = "\n".join(lines) + ("\n" if old.endswith("\n") else "")
            else:
                continue
            candidates.append((str(path), new))
        return candidates

    def _queue_edit(self, name: str, args: dict, diff: str) -> str:
        for edit_id, pending in self._pending_edits.items():
            if pending["name"] == name and pending["args"] == args:
                return edit_id
        edit_id = f"edit-{self._next_edit_id:04d}"
        self._next_edit_id += 1
        self._pending_edits[edit_id] = {"name": name, "args": dict(args), "diff": diff}
        return edit_id

    def apply_pending_edit(self, edit_id: str = "") -> tuple[str, bool]:
        edit_id = edit_id.strip()
        if not edit_id and len(self._pending_edits) == 1:
            edit_id = next(iter(self._pending_edits))
        pending = self._pending_edits.pop(edit_id, None)
        if not pending:
            return f"Unknown or expired edit id: {edit_id or '(none)'}", False
        result = self._execute_tool_with_safety(
            pending["name"], dict(pending["args"]), _edit_confirmed=True
        )
        self._refresh_final_report_after_approval()
        return result

    def reject_pending_edit(self, edit_id: str = "") -> tuple[str, bool]:
        edit_id = edit_id.strip()
        if not edit_id and len(self._pending_edits) == 1:
            edit_id = next(iter(self._pending_edits))
        pending = self._pending_edits.pop(edit_id, None)
        if not pending:
            return f"Unknown or expired edit id: {edit_id or '(none)'}", False
        result = f"Rejected {edit_id}; no file was changed.", True
        self._refresh_final_report_after_approval()
        return result

    def replace_pending_edit(self, edit_id: str, replacement_file: str) -> tuple[str, bool]:
        pending = self._pending_edits.get(edit_id.strip())
        if not pending:
            return f"Unknown or expired edit id: {edit_id}", False
        target = pending["args"].get("path")
        source = Path(replacement_file).expanduser().resolve()
        if not target or not source.is_file():
            return "Replacement file does not exist or pending edit has no single target.", False
        content = source.read_text(encoding="utf-8")
        args = {"path": target, "content": content}
        ok, diff = preview_mutation("write_file", args, self.working_dir)
        if not ok:
            return diff, False
        pending.update({"name": "write_file", "args": args, "diff": diff})
        return f"Updated {edit_id} preview:\n{diff}", True

    def pending_edits_summary(self) -> str:
        if not self._pending_edits:
            return "No file edits are pending."
        lines = [f"Pending edits ({len(self._pending_edits)}):"]
        for edit_id, pending in self._pending_edits.items():
            lines.append(
                f"  {edit_id}: {pending['name']} {pending['args'].get('path', '(multiple files)')}"
            )
        return "\n".join(lines)

    def _queue_confirmation(
        self, name: str, args: dict, safety_check: SafetyCheck, edit_confirmed: bool = False
    ) -> str:
        """Store an exact dangerous tool call until the user confirms or cancels it."""
        for confirmation_id, pending in self._pending_confirmations.items():
            if pending["name"] == name and pending["args"] == args:
                return confirmation_id

        confirmation_id = f"danger-{self._next_confirmation_id:04d}"
        self._next_confirmation_id += 1
        self._pending_confirmations[confirmation_id] = {
            "name": name,
            "args": dict(args),
            "reason": safety_check.reason,
            "details": safety_check.details,
            "edit_confirmed": edit_confirmed,
        }
        return confirmation_id

    def confirm_pending_operation(self, confirmation_id: str = "") -> tuple[str, bool]:
        """Execute one exact pending operation after explicit user confirmation."""
        confirmation_id = confirmation_id.strip()
        if not confirmation_id:
            if len(self._pending_confirmations) == 1:
                confirmation_id = next(iter(self._pending_confirmations))
            elif not self._pending_confirmations:
                return "No dangerous operation is pending confirmation.", False
            else:
                ids = ", ".join(self._pending_confirmations)
                return f"Multiple operations are pending; specify one: {ids}", False

        pending = self._pending_confirmations.pop(confirmation_id, None)
        if not pending:
            return f"Unknown or expired confirmation id: {confirmation_id}", False

        result = self._execute_tool_with_safety(
            pending["name"],
            dict(pending["args"]),
            _user_confirmed=True,
            _edit_confirmed=bool(pending.get("edit_confirmed")),
        )
        self._refresh_final_report_after_approval()
        return result

    def cancel_pending_operation(self, confirmation_id: str = "") -> tuple[str, bool]:
        """Cancel one pending dangerous operation without executing it."""
        confirmation_id = confirmation_id.strip()
        if not confirmation_id:
            if len(self._pending_confirmations) == 1:
                confirmation_id = next(iter(self._pending_confirmations))
            elif not self._pending_confirmations:
                return "No dangerous operation is pending confirmation.", False
            else:
                ids = ", ".join(self._pending_confirmations)
                return f"Multiple operations are pending; specify one: {ids}", False

        pending = self._pending_confirmations.pop(confirmation_id, None)
        if not pending:
            return f"Unknown or expired confirmation id: {confirmation_id}", False
        result = f"Cancelled {confirmation_id}; the operation was not executed.", True
        self._refresh_final_report_after_approval()
        return result

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

        lines = raw_args.count("\n") + raw_args.count("\\n")
        chars = len(raw_args)

        if name in ("write_file", "create_file"):
            if path_str:
                return f"[bold {ui.ORANGE}]⚡ Stream-Drafting File:[/] [bold {ui.CYAN}]{path_str}[/] [bold {ui.GOLD}]({lines} lines / {chars:,} bytes)[/]"
            return f"[bold {ui.ORANGE}]⚡ Stream-Drafting Code File...[/] [bold {ui.GOLD}]({lines} lines / {chars:,} bytes)[/]"

        elif name in ("edit_file", "patch_file", "multi_edit"):
            if path_str:
                return f"[bold {ui.ORANGE}]⚡ Surgical Code Edit:[/] [bold {ui.CYAN}]{path_str}[/] [bold {ui.GOLD}]({lines} lines / {chars:,} bytes)[/]"
            return f"[bold {ui.ORANGE}]⚡ Preparing Surgical Code Edit...[/] [bold {ui.GOLD}]({chars:,} bytes)[/]"

        elif name in ("run_command", "run_process", "process_run"):
            if cmd_str:
                clean_cmd = cmd_str.replace("\\n", " ").replace("\n", " ")
                return f"[bold {ui.ORANGE}]⚡ Guarded Shell Execution:[/] [bold {ui.WHITE}]{clean_cmd[:65]}[/]"
            return f"[bold {ui.ORANGE}]⚡ Preparing Guarded Shell Execution...[/]"

        elif name:
            return f"[bold {ui.ORANGE}]⚡ Executing Tool Matrix:[/] [bold {ui.CYAN}]{name}[/] [bold {ui.GOLD}]({chars:,} bytes)[/]"

        return f"[bold {ui.CYAN}]Thinking & Reasoning with {self.model_cfg['name']}...[/]"

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
                if hasattr(chunk, "usage") and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens or 0
                    completion_tokens = chunk.usage.completion_tokens or 0
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

        finally:
            live.stop()

        if prompt_tokens:
            self.total_prompt_tokens += prompt_tokens
        if completion_tokens:
            self.total_completion_tokens += completion_tokens
        if prompt_tokens or completion_tokens:
            self.budget.record_usage(prompt_tokens, completion_tokens)

        tool_calls = []
        for idx in sorted(tool_calls_accum.keys()):
            tc = tool_calls_accum[idx]
            if tc["name"]:
                if not tc.get("id"):
                    tc["id"] = f"call_{idx}_{int(time.time() * 1000)}"
                tool_calls.append(tc)

        if full_content:
            ui.console.print()  # Newline after streamed content

        return full_content, tool_calls

    def _handle_tool_calls_interactive(
        self, tool_calls: list[dict], *, emit_ui: bool = True
    ) -> tuple[list[dict], list[bool]]:
        """Execute tool calls, optionally rendering interactive progress."""
        results = []
        successes = []
        for tc in tool_calls:
            name = tc["name"]
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {}

            if emit_ui:
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
            elif name in ("run_command", "run_process", "process_run"):
                cmd_val = args.get("command", "")
                if name == "run_process":
                    cmd_val = shlex.join(str(item) for item in args.get("argv", []))
                exec_msg = f"Running command: {cmd_val[:60]}..."

            if emit_ui:
                with ui.console.status(
                    f"[bold {ui.ORANGE}]⚡ {exec_msg}[/]", spinner="bouncingBar"
                ):
                    result, success = self._execute_tool_with_safety(name, args)
            else:
                result, success = self._execute_tool_with_safety(name, args)

            if emit_ui:
                ui.print_tool_result(result, success)

            # Reflection
            verdict = self.reflector.reflect(name, args, result)
            if emit_ui and verdict.verdict == ReflectionVerdict.ESCALATE:
                ui.print_warning(f"⚠ Reflection: {verdict.suggestion}")

            # Cap tool content for context memory efficiency
            truncated_res = result
            if len(result) > 6000:
                truncated_res = (
                    result[:3000]
                    + f"\n\n... [truncated {len(result) - 6000} chars for context efficiency] ...\n\n"
                    + result[-3000:]
                )

            results.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": truncated_res,
                }
            )
            successes.append(success)

        return results, successes

    # ── Main Run Loop (Interactive CLI) ──────────────────────────────────

    def run(self, user_input: str) -> str:
        """
        Run one turn of the agent loop with full OS integration.
        Delegates to the canonical ExecutionPipeline.
        """
        # Reload project rules on each turn
        self._load_rules_and_preferences()
        self._update_system_prompt()

        from nexus.pipeline import ExecutionPipeline

        pipeline = ExecutionPipeline(self)
        result = pipeline.run(user_input, interactive=True, emit_ui=True)
        return result.response

    # ── Non-Interactive Run (Web API) ────────────────────────────────────

    def run_non_interactive(self, user_input: str) -> tuple[str, list[dict]]:
        """
        Run one turn and return (final_text, all_tool_events).
        Used by the web API for structured responses.
        Delegates to the canonical ExecutionPipeline.
        """
        self._load_rules_and_preferences()
        self._update_system_prompt()

        from nexus.pipeline import ExecutionPipeline

        pipeline = ExecutionPipeline(self)
        result = pipeline.run(user_input, interactive=False, emit_ui=False)
        return result.response, result.events

    def _run_hosted_turn(
        self,
        user_input: str,
        analysis: dict,
        plan: Any,
        interactive: bool = False,
        emit_ui: bool = False,
        max_turns_override: int | None = None,
    ) -> tuple[str, list[dict]]:
        """Run a standard hosted-model execution loop (single-node)."""
        _run_id = (
            self.run_ledger.session_id if hasattr(self, "run_ledger") and self.run_ledger else None
        )
        session = ExecutionSession(
            provider=self.client,
            max_turns=max_turns_override or self.max_turns,
            model_id=self.model_cfg["id"],
            run_id=_run_id,
            ledger=self.run_ledger,
        )
        engine = session.interactive

        def handle_tool(name, args):
            tc = [{"id": f"call_{time.time()}", "name": name, "arguments": json.dumps(args)}]
            res, successes = self._handle_tool_calls_interactive(tc, emit_ui=emit_ui)
            return successes[0], res[0]["content"]

        engine.tool_executor = handle_tool

        # Auto-activate skills
        try:
            self.skills.auto_activate(
                user_input,
                intent=analysis["intent"].value
                if hasattr(analysis["intent"], "value")
                else str(analysis.get("intent", "unknown")),
            )
            self._update_system_prompt()
        except Exception:
            pass

        self.messages.append({"role": "user", "content": user_input})
        events = engine.run_interactive(self._build_messages(), tools=self._get_tools())

        live = ui.LiveStatus() if emit_ui else None
        content = ""
        accumulated_events = []

        try:
            for event in events:
                if event.type == EventType.MODEL_REQUEST_STARTED:
                    if live:
                        live.start(f"Connecting to {self.model_cfg['name']}...")
                elif event.type == EventType.MODEL_REQUEST_COMPLETED:
                    if live:
                        live.stop()
                    accumulated_events.append(
                        {
                            "type": "model_turn",
                            "model": event.model,
                            "usage": event.usage,
                            "node": "hosted",
                        }
                    )
                elif event.type == EventType.MODEL_STREAM_CHUNK:
                    if live and live._is_active:
                        live.stop()
                    if emit_ui:
                        ui.console.print(event.text, end="", style=ui.WHITE, highlight=False)
                elif event.type == EventType.TOOL_CALL_STARTED:
                    if live:
                        live.update(f"Running tool {event.tool_name}...")
                elif event.type == EventType.TOOL_CALL_COMPLETED:
                    accumulated_events.append(
                        {
                            "type": "tool_call",
                            "name": event.tool_name,
                            "args": event.arguments,
                            "result": event.result,
                            "success": event.success,
                            "node": "interactive",
                        }
                    )
                elif event.type == EventType.RUN_FAILED:
                    raise RuntimeError(event.error)
                elif event.type == EventType.RUN_COMPLETED:
                    content = event.content
        except Exception as e:
            if live:
                live.stop()
            error_msg = str(e)
            if isinstance(e, BudgetExceeded):
                content = f"BLOCKED: {error_msg}"
                if hasattr(self, "run_ledger") and self.run_ledger:
                    self.run_ledger.append_event("budget", status="blocked", detail=error_msg)
                if emit_ui:
                    ui.print_error(content)
                return content, accumulated_events

            is_rate_limit = (
                "429" in error_msg.lower()
                or "rate" in error_msg.lower()
                or "resourceexhausted" in error_msg.lower()
                or "too many requests" in error_msg.lower()
            )
            if (
                (is_rate_limit or "Nexus AI Provider Failover Error" in error_msg)
                and self.enable_nova_fallback
                and self.local_intern_enabled
            ):
                if emit_ui:
                    ui.print_warning(
                        "Hosted providers are unavailable — using the explicitly enabled local Nova fallback."
                    )
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                return self._run_nova_turn(user_input, emit_ui=emit_ui)

            if emit_ui:
                ui.print_error(f"API error: {error_msg}")
            return f"Error: {error_msg}", accumulated_events

        if content:
            content = self._guard_completion_claims(content)
            self.messages.append({"role": "assistant", "content": content})
            if emit_ui:
                ui.console.print()

        if emit_ui:
            ui.print_response_complete()
        self._auto_save()

        # ── Post-plan verification ────────────────────────────────
        if plan and hasattr(plan, "steps"):
            current_step = next((s for s in plan.steps if s.status == TaskStatus.IN_PROGRESS), None)
            if current_step:
                tool_events = [
                    event
                    for event in accumulated_events
                    if isinstance(event, dict) and event.get("type") == "tool_call"
                ]
                successful_tools = {
                    str(event.get("name", ""))
                    for event in tool_events
                    if event.get("success", False)
                }
                mutation_tools = {"write_file", "edit_file", "patch_file", "multi_edit"}
                expected_tools = set(current_step.tools_needed)
                expected_mutation = bool(expected_tools & mutation_tools)
                expected_command = bool(expected_tools & {"run_command", "run_process"})
                mutated = bool(successful_tools & mutation_tools)
                contract_missing = (
                    (expected_mutation and not mutated)
                    or (expected_command and not successful_tools & {"run_command", "run_process"})
                    or (expected_tools and not successful_tools)
                )
                response_failed = (
                    (content or "").lstrip().upper().startswith(("ERROR:", "BLOCKED:"))
                )
                if response_failed or contract_missing:
                    self.planner.advance_step(
                        current_step.id,
                        TaskStatus.FAILED,
                        (
                            "The model stopped with an execution error."
                            if response_failed
                            else "The step ended without satisfying its required tool contract."
                        ),
                    )
                elif mutated:
                    # Read-only diagnostic steps may inspect a broken tree. A
                    # mutating step must leave syntax and imports coherent.
                    syntax_check = self.verifier.verify_syntax()
                    import_check = self.verifier.verify_imports()
                    syntax_ok = syntax_check.status in {
                        CheckStatus.PASSED,
                        CheckStatus.NOT_APPLICABLE,
                    }
                    imports_ok = import_check.status in {
                        CheckStatus.PASSED,
                        CheckStatus.NOT_APPLICABLE,
                    }
                    if syntax_ok and imports_ok:
                        self.planner.advance_step(
                            current_step.id,
                            TaskStatus.COMPLETED,
                            "Step executed successfully",
                        )
                    else:
                        err_msg = ""
                        if not syntax_ok:
                            err_msg += f"Syntax error: {syntax_check.output}\n"
                        if not imports_ok:
                            err_msg += f"Import error: {import_check.output}\n"
                        self.planner.advance_step(current_step.id, TaskStatus.FAILED, err_msg)
                else:
                    self.planner.advance_step(
                        current_step.id, TaskStatus.COMPLETED, "Step executed successfully"
                    )

        if plan and plan.is_complete:
            if emit_ui:
                ui.print_info("📋 Plan complete. Running verification...")
            try:
                report = self._record_verification_report(self.verifier.run_all())
                if emit_ui:
                    ui.console.print(report.format_report())
                if report.all_passed:
                    self.hooks.fire(
                        HookEvent.ON_PLAN_COMPLETE, HookContext(event=HookEvent.ON_PLAN_COMPLETE)
                    )
                else:
                    self.hooks.fire(
                        HookEvent.ON_TEST_FAIL, HookContext(event=HookEvent.ON_TEST_FAIL)
                    )
            except Exception:
                pass

        return content or "", accumulated_events

    def resume_interrupted(self, run_id: str) -> tuple[str, list[dict]]:
        """Continue an interrupted run from its persisted plan/checkpoint."""
        from nexus.planner import ExecutionPlan

        catalog = RunCatalog()
        turn_dir = catalog.resolve(run_id)
        inspected = catalog.inspect(run_id)
        state = inspected.get("state", {})
        if state.get("status") in {
            RunStatus.VERIFIED.value,
            RunStatus.ROLLED_BACK.value,
        }:
            raise ValueError(f"Run is already terminal: {state.get('status')}")
        request_record = inspected.get("request", {})
        expected_workspace = (
            Path(request_record.get("working_dir") or self.working_dir).expanduser().resolve()
        )
        if expected_workspace != Path(self.working_dir).resolve():
            raise ValueError(
                f"Resume workspace mismatch: expected {expected_workspace}, got {self.working_dir}"
            )
        plan_data = inspected.get("plan", {})
        if not plan_data.get("id"):
            raise ValueError("Interrupted run has no resumable execution plan")
        plan = ExecutionPlan.from_dict(plan_data)
        # A killed process can leave a step in progress, while a bounded model
        # turn can deliberately close it as failed. Explicit recovery retries
        # only those unfinished steps and preserves completed checkpoints.
        for step in plan.steps:
            if step.status in {TaskStatus.IN_PROGRESS, TaskStatus.FAILED}:
                step.status = TaskStatus.PENDING
                step.error = ""
                step.completed_at = ""
        plan.status = TaskStatus.PENDING
        next_step = plan.next_step
        plan.current_step = next_step.id if next_step else None
        self.planner.current_plan = plan
        session_id = turn_dir.parent.name
        self.conversation_id = session_id
        self.history = FileHistory(session_id)
        self.evidence = EvidenceTrail(session_id)
        self.run_ledger = RunLedger(session_id, self.working_dir)
        saved = self.memory.load_conversation(session_id)
        if saved:
            self.messages = list(saved.get("messages", []))

        original = str(request_record.get("request", "")).strip()
        checkpoint = inspected.get("checkpoint", {})
        pending = [
            step.id
            for step in plan.steps
            if step.status in {TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.FAILED}
        ]
        completed = [step.id for step in plan.steps if step.status == TaskStatus.COMPLETED]
        resume_prompt = (
            f"{original}\n\n"
            "[NEXUS CRASH RECOVERY]\n"
            f"Resume from checkpoint {checkpoint.get('checkpoint', 'none')} "
            f"({checkpoint.get('label', 'no label')}).\n"
            f"Already completed task ids: {completed or 'none'}.\n"
            f"Continue only pending/failed task ids: {pending or 'none'}.\n"
            "Re-read current disk state, do not repeat verified mutations, and rerun "
            "the required deterministic checks before claiming completion."
        )
        self._resume_plan_override = plan
        self._resume_objective_override = original
        self._resume_analysis_override = {
            "intent": plan.intent,
            "difficulty": plan.difficulty,
            "plan_type": plan.plan_type,
            "skills_needed": plan.skills_needed,
            "resume_parent": f"{session_id}/{turn_dir.name}",
            "resume_plan": plan.to_dict(),
        }
        return self.run_non_interactive(resume_prompt)

    def _run_two_node_turn(
        self, user_input: str, analysis: dict, emit_ui: bool = True
    ) -> tuple[str, list[dict]]:
        """Run a hosted-model turn through Ceiling planning and Nova Intern execution."""
        from nexus.two_node_backend import TwoNodeBackend

        events: list[dict] = []
        self.messages.append({"role": "user", "content": user_input})

        backend = TwoNodeBackend(
            client=self.client,
            ceiling_model_id=self.model_cfg["id"],
            ceiling_model_name=self.model_cfg["name"],
            working_dir=self.working_dir,
            intern_model=self.model_cfg.get("intern_model", "nova_codex"),
            run_ledger=self.run_ledger,
        )

        try:
            if emit_ui:
                live = ui.LiveStatus()
                live.start("Hosted planner and local intern are preparing the task graph...")
                try:
                    result = backend.run(user_input, planner_analysis=analysis)
                finally:
                    live.stop()
            else:
                result = backend.run(user_input, planner_analysis=analysis)
        except Exception as e:
            if emit_ui:
                ui.print_warning(f"Two-node backend error: {e}")
            if self.messages and self.messages[-1]["role"] == "user":
                self.messages.pop()
            raise RuntimeError(f"Two-node backend failed: {e}") from e

        def record_result(candidate, phase: str) -> None:
            if candidate.execution_plan is not None:
                self._active_plan = candidate.execution_plan
                self.planner.current_plan = candidate.execution_plan
            self.run_ledger.append_model_call(
                role=f"ceiling_{phase}",
                model=self.model_cfg["id"],
                status=("verified" if candidate.review_approved else "failed"),
                usage=self.budget.snapshot().get("usage", {}),
                detail=candidate.review_summary,
            )
            self.evidence.append(
                kind="independent_review",
                claim=f"independent reviewer evaluated {phase} candidate",
                status="verified" if candidate.review_approved else "failed",
                raw_output=candidate.review_summary,
                metadata={"findings": candidate.review_findings},
            )
            for execution in candidate.executions:
                if execution.node.startswith("Nova") and not execution.escalated:
                    self.routing_stats["nova_tasks"] += 1
                else:
                    self.routing_stats["ceiling_tasks"] += 1
                self.routing_stats["nova_retries"] += max(0, execution.attempts - 1)
                if execution.escalated:
                    self.routing_stats["escalations"] += 1
                self.evidence.append(
                    kind="routing",
                    claim=f"subtask {execution.task.id} routed to {execution.node}",
                    status="verified" if execution.proposals else "failed",
                    raw_output=(
                        execution.guardrail_log + "\n\n[RAW MODEL OUTPUT]\n" + execution.raw_output
                    ).strip(),
                    metadata={
                        "reason": execution.route_reason,
                        "attempts": execution.attempts,
                        "verdict": execution.verdict,
                        "escalated": execution.escalated,
                        "failure_kind": execution.failure_kind,
                    },
                )

        def apply_result(candidate, phase: str) -> list[str]:
            changed: list[str] = []
            for proposal in candidate.proposals:
                args = dict(proposal.args)
                display_args = {
                    key: value for key, value in args.items() if key != "_nova_guardrail"
                }
                if emit_ui:
                    ui.print_tool_call(proposal.name, display_args)
                tool_result, success = self._execute_tool_with_safety(proposal.name, args)
                if emit_ui:
                    ui.print_tool_result(tool_result, success)
                events.append(
                    {
                        "type": "tool_call",
                        "name": proposal.name,
                        "args": display_args,
                        "result": tool_result,
                        "success": success,
                        "node": phase,
                        "guardrail": proposal.guardrail_summary,
                    }
                )
                if success:
                    path = str(display_args.get("path", ""))
                    if path:
                        changed.append(path)
            return changed

        breakdowns = [result.format_breakdown()]
        record_result(result, "initial")

        if not result.review_approved and result.review_findings:
            repair_analysis = {
                key: value for key, value in analysis.items() if key != "resume_plan"
            }
            focused_request = (
                f"{user_input}\n\nIndependent review rejected the candidate. "
                "Produce the smallest complete repair addressing only these findings:\n"
                + "\n".join(f"- {item}" for item in result.review_findings)
            )
            repair_result = backend.run(
                focused_request,
                planner_analysis=repair_analysis,
            )
            record_result(repair_result, "review_repair")
            breakdowns.append(repair_result.format_breakdown())
            result = repair_result

        changed_paths = apply_result(result, "two-node")
        applied = bool(changed_paths) and all(
            event.get("success", False) for event in events if event.get("type") == "tool_call"
        )
        recovered_without_edits = bool(
            result.review_approved
            and not result.proposals
            and result.execution_plan is not None
            and result.execution_plan.steps
            and all(step.status == TaskStatus.COMPLETED for step in result.execution_plan.steps)
            and any(
                execution.route_reason == "recovered verified checkpoint"
                for execution in result.executions
            )
        )
        if applied:
            security_result, security_ok = self._execute_tool_with_safety(
                "security_scan",
                {"paths": changed_paths},
            )
            events.append(
                {
                    "type": "tool_call",
                    "name": "security_scan",
                    "args": {"paths": changed_paths},
                    "result": security_result,
                    "success": security_ok,
                    "node": "nexus-verifier",
                }
            )
        if applied or recovered_without_edits:
            verification_report = self._record_verification_report(self.verifier.run_all())
            if emit_ui:
                ui.console.print(verification_report.format_report())
            if not verification_report.all_passed:
                repair_analysis = {
                    key: value for key, value in analysis.items() if key != "resume_plan"
                }
                focused_request = (
                    f"{user_input}\n\nThe candidate was applied in an isolated workspace, "
                    "but deterministic verification failed. Repair only the failing checks "
                    "and preserve already passing behavior.\n\n"
                    f"{verification_report.format_report()}"
                )
                repair_result = backend.run(
                    focused_request,
                    planner_analysis=repair_analysis,
                )
                record_result(repair_result, "verification_repair")
                breakdowns.append(repair_result.format_breakdown())
                if repair_result.review_approved:
                    apply_result(repair_result, "two-node-repair")
                    rerun = self._record_verification_report(self.verifier.run_all())
                    if emit_ui:
                        ui.console.print(rerun.format_report())

        breakdown = "\n\n".join(breakdowns)
        if emit_ui:
            ui.console.print(breakdown)
        breakdown = self._guard_completion_claims(breakdown)
        self.messages.append({"role": "assistant", "content": breakdown})
        self._auto_save()
        return breakdown, events

    def _run_nova_turn(self, user_input: str, emit_ui: bool = True) -> tuple[str, list[dict]]:
        """Run one turn through the local Nova pipeline backend."""
        from nexus.nova_backend import NovaBackendError, NovaPipelineBackend

        events: list[dict] = []
        self._load_rules_and_preferences()
        self.messages.append({"role": "user", "content": user_input})

        backend = NovaPipelineBackend(
            model=self.model_cfg.get("ollama_model", "nova_codex"),
            working_dir=self.working_dir,
        )

        try:
            if emit_ui:
                live = ui.LiveStatus()
                live.start("Running Nova 3B through local guardrails...")
                try:
                    nova_result = backend.run(user_input)
                finally:
                    live.stop()
            else:
                nova_result = backend.run(user_input)
        except NovaBackendError as e:
            content = f"Nova guardrails blocked the output: {e}"
            if emit_ui:
                ui.print_error(content)
            if self.messages and self.messages[-1].get("role") == "user":
                self.messages.pop()
            raise RuntimeError(content) from e
        except Exception as e:
            content = f"Nova backend error: {e}"
            if emit_ui:
                ui.print_error(content)
            if self.messages and self.messages[-1].get("role") == "user":
                self.messages.pop()
            raise RuntimeError(content) from e

        self.routing_stats["nova_tasks"] += 1
        self.run_ledger.append_model_call(
            role="intern",
            model=self.model_cfg.get("ollama_model", "nova_codex"),
            status="completed" if nova_result.raw_output else "failed",
            detail=(
                f"guarded proposals={len(nova_result.proposals)}; "
                f"declared_test={bool(nova_result.test_command)}"
            ),
        )

        if emit_ui and nova_result.raw_output:
            ui.console.print(nova_result.raw_output)
        if emit_ui and nova_result.guardrail_output:
            ui.print_info("Nova guardrail verdicts:")
            ui.console.print(nova_result.guardrail_output)

        # Structured/headless callers receive the same complete model and
        # guardrail transcript that interactive users see.  This is evidence,
        # not a shortened summary, so rejected generations remain auditable.
        events.append(
            {
                "type": "model_trace",
                "node": "nova",
                "raw_output": nova_result.raw_output,
                "guardrail_output": nova_result.guardrail_output,
            }
        )
        events.append(
            {
                "type": "model_turn",
                "node": "nova",
                "proposals": len(nova_result.proposals),
                "declared_test": bool(nova_result.test_command),
            }
        )

        mutated = False
        proposal_failed = False
        for proposal in nova_result.proposals:
            args = dict(proposal.args)
            display_args = {k: v for k, v in args.items() if k != "_nova_guardrail"}
            if emit_ui:
                ui.print_tool_call(proposal.name, display_args)
            result, success = self._execute_tool_with_safety(proposal.name, args)
            if emit_ui:
                ui.print_tool_result(result, success)
            events.append(
                {
                    "type": "tool_call",
                    "name": proposal.name,
                    "args": display_args,
                    "result": result,
                    "success": success,
                    "nova_guardrail": proposal.guardrail_summary,
                }
            )
            if success and proposal.name in {
                "write_file",
                "edit_file",
                "patch_file",
                "multi_edit",
                "replace_file_content",
                "multi_replace_file_content",
                "write_to_file",
            }:
                mutated = True
            if not success:
                proposal_failed = True

        test_failed = False
        if mutated and not proposal_failed and nova_result.test_command:
            test_result, test_success, evidence_id = self._run_declared_test_command(
                nova_result.test_command,
                source="nova",
                emit_ui=emit_ui,
            )
            test_failed = not test_success
            events.append(
                {
                    "type": "tool_call",
                    "name": "run_command",
                    "args": {"command": nova_result.test_command},
                    "result": test_result,
                    "success": test_success,
                    "node": "nova-declared-test",
                    "evidence_id": evidence_id,
                }
            )

        final_text = nova_result.assistant_text
        if proposal_failed:
            final_text += (
                "\n\nOne or more guarded file operations failed; completion is unverified."
            )
        if test_failed:
            final_text += "\n\nThe model-declared acceptance test failed; completion is unverified."
        final_content = self._guard_completion_claims(final_text)
        if emit_ui:
            ui.print_response_complete()
        self.messages.append({"role": "assistant", "content": final_content})
        self._auto_save()
        return final_content, events

    # ── Subagent Integration ─────────────────────────────────────────────

    def spawn_subagent(self, template_name: str, task: str) -> str:
        """Spawn a subagent from a template and execute its task."""
        subagent = create_subagent(template_name, task, self.working_dir)
        if not subagent:
            return f"❌ Unknown subagent template: {template_name}"

        orchestrator = SubagentOrchestrator(
            api_key=self._api_key,
            model_id=self.model_key,
            working_dir=self.working_dir,
        )
        result = orchestrator.run_single(subagent)

        evidence_record = self.evidence.append(
            kind="subagent",
            claim=f"subagent {template_name} completed its bounded task",
            status="verified" if result.succeeded else "failed",
            raw_output=result.summary,
            metadata={
                "task": task,
                "duration_ms": result.duration_ms,
                "tool_calls": result.tool_calls_made,
                "files_touched": result.files_touched,
                "errors": result.errors,
            },
        )
        if self.run_ledger.turn_dir:
            self.run_ledger.append_event(
                "subagent_finished",
                status="verified" if result.succeeded else "failed",
                detail=result.summary[:1000],
                metadata={
                    "subagent": template_name,
                    "task": task,
                    "evidence_id": evidence_record.id,
                    "files_touched": result.files_touched,
                },
            )

        self.hooks.fire(
            HookEvent.ON_SUBAGENT_COMPLETE,
            HookContext(
                event=HookEvent.ON_SUBAGENT_COMPLETE,
                metadata={"subagent": template_name, "task": task},
            ),
        )

        return result.format_report()

    def run_verification(self, checks: list[str] | None = None) -> str:
        """Run verification checks and return the report."""
        check_types = None
        if checks:
            valid = {item.value for item in CheckType}
            check_types = [CheckType(c) for c in checks if c in valid]
        report = self._record_verification_report(self.verifier.run_all(check_types))
        return report.format_report()

    def _run_declared_test_command(
        self,
        command: str,
        *,
        source: str,
        emit_ui: bool = False,
    ) -> tuple[str, bool, str]:
        """Execute a model-declared test through normal policy and persist test evidence."""
        if emit_ui:
            ui.print_info(f"Running {source}-declared acceptance test: {command}")
        output, success = self._execute_tool_with_safety(
            "run_command",
            {"command": command, "cwd": self.working_dir},
        )
        exit_code = command_exit_code(output)
        verified = bool(success and exit_code == 0)
        record = self.evidence.append(
            kind="verification_check",
            claim=f"{source}-declared acceptance test",
            status="verified" if verified else "failed",
            tool="model_declared_test",
            command=command,
            exit_code=exit_code,
            raw_output=output,
            metadata={"check_type": "test", "source": source},
        )
        if self.run_ledger.turn_dir:
            self.run_ledger.store_artifact(
                "tests",
                f"model-declared-{source}.txt",
                (
                    f"command: {command}\n"
                    f"status: {'passed' if verified else 'failed'}\n"
                    f"exit_code: {exit_code}\n\n{output}\n"
                ),
            )
        return output, verified, record.id

    def _record_verification_report(self, report):
        """Mirror deterministic project checks into the evidence trail."""
        for index, check in enumerate(report.checks, 1):
            status = "verified" if check.passed else "failed"
            exit_code = 0 if check.passed else 1
            self.evidence.append(
                kind="verification_check",
                claim=f"project verification: {check.check_type.value}",
                status=status,
                tool="verification_engine",
                command=check.command,
                exit_code=exit_code,
                raw_output=check.output,
                metadata={
                    "duration_ms": check.duration_ms,
                    "check_status": check.status.value,
                    "check_type": check.check_type.value,
                },
            )
            if self.run_ledger.turn_dir:
                self.run_ledger.store_artifact(
                    "tests",
                    f"{index:02d}-{check.check_type.value}.txt",
                    (
                        f"command: {check.command}\n"
                        f"status: {check.status.value}\n"
                        f"duration_ms: {check.duration_ms}\n\n"
                        f"{check.output}\n"
                    ),
                )
        return report

    def verify_evidence(self, count: int = 10) -> str:
        matched, report = self.evidence.verify_recent(count)
        reruns = []
        verification_pattern = (
            "test",
            "pytest",
            "jest",
            "vitest",
            "ruff",
            "mypy",
            "tsc",
            "lint",
            "build",
            "compile",
            "cargo check",
            "go vet",
            "node --check",
        )
        prior_records = self.evidence.records(max(1, count))
        for record in prior_records:
            command = record.get("command", "")
            if record.get("kind") != "command" or not command:
                continue
            if not any(marker in command.lower() for marker in verification_pattern):
                reruns.append(f"SKIPPED non-verification command: {command}")
                continue
            result, success = self._execute_tool_with_safety(
                "run_command", {"command": command, "cwd": self.working_dir}
            )
            matched = matched and success
            reruns.append(f"RERUN {'PASS' if success else 'FAIL'}: {command}\n{result}")
        if reruns:
            report += "\n\nCommand re-runs:\n" + "\n".join(reruns)
        self.evidence.append(
            kind="evidence_audit",
            claim=f"re-verified the last {count} completion claims",
            status="verified" if matched else "failed",
            raw_output=report,
        )
        return report

    def get_cost_dashboard(self) -> str:
        local = self.routing_stats["nova_tasks"]
        paid = self.routing_stats["ceiling_tasks"]
        budget = self.budget.snapshot()
        usage = budget["usage"]
        limits = budget["limits"]
        currency = (
            f"${usage['estimated_cost_usd']:.6f}"
            if limits["input_price_per_million"] is not None
            else "unavailable (no configured provider price table)"
        )
        return (
            "Routing dashboard\n"
            f"  Local Nova subtasks: {local}\n"
            f"  Ceiling subtasks: {paid}\n"
            f"  Nova retries: {self.routing_stats['nova_retries']}\n"
            f"  Escalations: {self.routing_stats['escalations']}\n"
            f"  Hosted calls avoided: {local}\n"
            f"  Hosted calls used: {usage['hosted_calls']}\n"
            f"  Prompt tokens: {usage['prompt_tokens']}\n"
            f"  Completion tokens: {usage['completion_tokens']}\n"
            f"  Estimated hosted cost: {currency}\n"
            f"  Hard limits: {json.dumps(limits, sort_keys=True)}"
        )

    def get_trust_summary(self) -> str:
        decisions = self.trust.scan_project()
        if not decisions:
            return "No trust-sensitive project config files found."
        lines = ["Trust-sensitive config:"]
        for item in decisions:
            state = "APPROVED" if item.approved else ("CHANGED" if item.changed else "PENDING")
            lines.append(f"  {state}: {item.path} sha256={item.digest}")
            if not item.approved and item.diff:
                lines.append(item.diff)
        return "\n".join(lines)

    def _guard_completion_claims(self, content: str) -> str:
        """Prevent unsupported success prose from becoming Nexus' final status."""
        start = getattr(self, "_turn_evidence_start", 0)
        records = self.evidence.records()[start:]
        warnings = []
        if self._pending_edits:
            warnings.append(
                f"NOT APPLIED: {len(self._pending_edits)} file diff(s) still require /apply approval."
            )
        claims_tests = bool(
            re.search(
                r"\b(tests?|checks?|build)\b.{0,30}\b(pass(?:ed|ing)?|green|success)", content, re.I
            )
        )
        if claims_tests:
            has_test_evidence = any(
                record.get("kind") == "command"
                and record.get("status") == "verified"
                and record.get("exit_code") == 0
                and any(
                    term in record.get("command", "").lower()
                    for term in ("test", "pytest", "jest", "build", "check")
                )
                for record in records
            )
            if not has_test_evidence:
                warnings.append(
                    "UNVERIFIED TEST CLAIM: no real passing test/build command was recorded this turn."
                )
        if warnings:
            return "\n".join(f"⚠️ {warning}" for warning in warnings) + "\n\n" + content
        return content

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
