"""
Agent — the core agentic loop upgraded to a full Agent Operating System.

Integrates Planning, Reflection, Context Management, Safety, project rules (NEXUS.md),
user preferences, skills, subagents, hooks, MCP, and plugins.
"""

import json
import os
import re
import shlex
import sys
import time
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from nexus import ui
from nexus.api import NvidiaClient
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
from nexus.models import DEFAULT_MODEL, MODELS, resolve_model_key
from nexus.package_guard import PackageGuard
from nexus.paths import nexus_home

# Phase 1: Core Engine Imports
from nexus.planner import IntentType, PlanningEngine, PlanType, TaskStatus
from nexus.plugins.loader import PluginLoader
from nexus.policy import PermissionDecision, PolicyLoader
from nexus.project_memory import ProjectMemory
from nexus.reflection import ReflectionEngine, ReflectionVerdict
from nexus.repo_graph import RepoGraph
from nexus.run_catalog import RunCatalog
from nexus.run_state import CriterionResult, CriterionStatus, RunLedger, RunStatus
from nexus.safety import SafetyCheck, SafetyLayer, SafetyLevel

# Phase 2: Skills & Subagents
from nexus.skills.loader import SkillLoader, SkillRegistry
from nexus.subagents.orchestrator import SubagentOrchestrator
from nexus.subagents.templates import create_subagent
from nexus.tools import TOOL_DEFINITIONS, execute_tool, tool_get_project_structure, tool_git_status
from nexus.trust import TrustStore
from nexus.user_memory import UserMemory
from nexus.verification import CheckType, VerificationEngine
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
        working_dir: str | None = None,
        permission_mode: str = "default",
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        additional_dirs: list[str] | None = None,
        max_turns: int = 50,
        workspace_isolation: bool = False,
        max_hosted_calls: int | None = None,
        max_prompt_tokens: int | None = None,
        max_completion_tokens: int | None = None,
        max_cost_usd: float | None = None,
        input_price_per_million: float | None = None,
        output_price_per_million: float | None = None,
    ):
        self.source_working_dir = str(Path(working_dir or os.getcwd()).resolve())
        self.conversation_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.worktree: GitWorktreeSession | None = None
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
        else:
            self.working_dir = self.source_working_dir
        # P0-3 FIX: Remove os.chdir(self.working_dir) to prevent global process state pollution

        # Model and backend selection
        resolved_key = resolve_model_key(model_key) or DEFAULT_MODEL
        self.model_key = resolved_key
        self.model_cfg = MODELS[resolved_key]
        self._api_key = api_key
        self.budget = BudgetController(
            BudgetLimits(
                max_hosted_calls=max_hosted_calls,
                max_prompt_tokens=max_prompt_tokens,
                max_completion_tokens=max_completion_tokens,
                max_cost_usd=max_cost_usd,
                input_price_per_million=input_price_per_million,
                output_price_per_million=output_price_per_million,
            )
        )
        self.client = (
            None
            if self._is_nova_model()
            else BudgetedClient(NvidiaClient(api_key=api_key), self.budget)
        )

        # State
        self.messages: list[dict] = []
        self.base_system_prompt = SYSTEM_PROMPT
        self.system_prompt = SYSTEM_PROMPT
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.permission_mode = permission_mode
        self.allowed_tools = set(allowed_tools or [])
        self.disallowed_tools = set(disallowed_tools or [])
        self.additional_dirs = [str(Path(item).expanduser().resolve()) for item in (additional_dirs or [])]
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
        self._permissions_used: set[str] = set()
        self._network_calls: list[str] = []
        self.package_guard = PackageGuard()
        self.trust = TrustStore(self.working_dir)
        self.policy = PolicyLoader(self.working_dir).load()
        self.extensions = ExtensionRegistry()
        self.extensions.discover()
        self.routing_stats = {"nova_tasks": 0, "ceiling_tasks": 0, "nova_retries": 0, "escalations": 0}

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
        except Exception:
            pass  # MCP is optional and never loaded without content approval

        # ── Phase 3: Plugins ─────────────────────────────────────────────
        self.plugin_loader = PluginLoader(self.working_dir)
        try:
            local_plugin_configs = list((Path(self.working_dir) / "nexus_plugins").glob("*/plugin.json"))
            local_plugins_trusted = all(self.trust.is_approved(path) for path in local_plugin_configs)
            for plugin in self.plugin_loader.discover_and_load() if local_plugins_trusted else []:
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
            mcp_config = nexus_home() / "mcp_servers.json"
            if mcp_config.exists() and not self.trust.is_approved(mcp_config):
                self.mcp.disconnect_all()
            local_plugin_configs = list((Path(self.working_dir) / "nexus_plugins").glob("*/plugin.json"))
            if any(not self.trust.is_approved(path) for path in local_plugin_configs):
                self.plugin_loader.plugins.clear()
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
        except Exception:
            pass

    def _update_system_prompt(self):
        """Combine base prompt with project memory, user preferences, and active skills."""
        prompt = self.base_system_prompt

        # Project memory (NEXUS.md rules)
        try:
            rules_paths = self.project_mem.get_rules_paths()
            addon = (
                self.project_mem.get_prompt_addon()
                if not rules_paths
                or all(self.trust.is_approved(path) for path in rules_paths)
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

        self.system_prompt = prompt

    def set_model(self, model_key: str) -> bool:
        """Switch to a different model."""
        resolved_key = resolve_model_key(model_key)
        if not resolved_key:
            return False
        cfg = MODELS[resolved_key]
        if cfg.get("backend") != "nova" and self.client is None:
            try:
                self.client = BudgetedClient(
                    NvidiaClient(api_key=self._api_key),
                    self.budget,
                )
            except ValueError:
                return False
        self.model_key = resolved_key
        self.model_cfg = cfg
        self.hooks.fire(HookEvent.ON_MODEL_SWITCH, HookContext(
            event=HookEvent.ON_MODEL_SWITCH,
            metadata={"model": resolved_key},
        ))
        return True

    def _is_nova_model(self) -> bool:
        """Return True when the active model uses the local Nova backend."""
        return self.model_cfg.get("backend") == "nova"

    def _should_use_two_node(self, analysis: dict) -> bool:
        """Use Ceiling+Intern for coding/workspace tasks handled by hosted models."""
        if self._is_nova_model() or not self.model_cfg.get("supports_tools"):
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
                self.planner._generate_verification(
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

    def _finish_managed_run(
        self,
        content: str,
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Evaluate evidence and write a machine-readable final report."""
        if not self.run_ledger.turn_dir:
            return {}
        evidence = self.evidence.records()[getattr(self, "_turn_evidence_start", 0) :]
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
            and not (
                item.get("kind") == "command"
                and item.get("command", "") in successful_command_text
            )
            and not (
                item.get("kind") == "behavioral_verification"
                and latest_behavioral_status.get(item.get("tool", "")) == "verified"
            )
        ]
        verified_mutations = [
            item
            for item in evidence
            if item.get("kind") == "file_mutation" and item.get("status") == "verified"
        ]
        passing_behavioral = [
            item
            for item in evidence
            if item.get("kind") == "behavioral_verification"
            and item.get("status") == "verified"
        ]
        approved_reviews = [
            item
            for item in evidence
            if item.get("kind") == "independent_review"
            and item.get("status") == "verified"
        ]
        passing_checks = [
            item
            for item in passing_commands
            if any(
                term in item.get("command", "").lower()
                for term in (
                    "test",
                    "pytest",
                    "jest",
                    "vitest",
                )
            )
        ]

        def matching_checks(criterion: str) -> list[dict[str, Any]]:
            lowered = criterion.lower()
            if "lint" in lowered or "type" in lowered:
                markers = ("lint", "ruff", "mypy", "pyright", "tsc", "clippy", "vet")
            elif "security" in lowered or "vulnerab" in lowered:
                markers = ("audit", "bandit", "semgrep", "security", "safety")
            elif "build" in lowered or "compile" in lowered:
                markers = ("build", "compile", "cargo check", "go test", "tsc")
            elif "test" in lowered or "regression" in lowered or "coverage" in lowered:
                markers = ("test", "pytest", "jest", "vitest", "rspec", "phpunit")
            else:
                return []
            return [
                item
                for item in passing_commands
                if any(marker in item.get("command", "").lower() for marker in markers)
            ]

        plan = self._active_plan
        if plan is not None:
            criteria_text = list(plan.acceptance_criteria)
            self.run_ledger.record_plan(plan)
        else:
            criteria_text = self.planner._generate_acceptance_criteria(
                self._active_objective,
                self._active_analysis.get("intent", IntentType.UNKNOWN),
                self.planner._generate_verification(
                    self._active_analysis.get("intent", IntentType.UNKNOWN),
                    self._active_analysis.get("skills_needed", []),
                ),
            )

        results: list[CriterionResult] = []
        for criterion in criteria_text:
            lowered = criterion.lower()
            if "unrelated files" in lowered:
                permitted = list(getattr(plan, "permitted_files", []) or [])
                outside = []
                for item in changes:
                    changed_path = Path(item["filepath"]).resolve()
                    if not _is_relative_to(changed_path, Path(self.working_dir)):
                        outside.append(item["filepath"])
                        continue
                    relative = changed_path.relative_to(
                        Path(self.working_dir).resolve()
                    ).as_posix()
                    if permitted and not any(
                        fnmatch(relative, pattern) or relative == pattern
                        for pattern in permitted
                    ):
                        outside.append(relative)
                results.append(
                    CriterionResult(
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
                )
            elif "fingerprinted" in lowered:
                mutation_records = [
                    item for item in evidence if item.get("kind") == "file_mutation"
                ]
                satisfied = bool(mutation_records) and all(
                    item.get("status") == "verified" for item in mutation_records
                )
                results.append(
                    CriterionResult(
                        criterion,
                        (
                            CriterionStatus.SATISFIED
                            if satisfied
                            else CriterionStatus.UNVERIFIED
                        ),
                        evidence_ids=[item["id"] for item in mutation_records],
                        detail=(
                            "Every recorded mutation passed disk verification."
                            if satisfied
                            else "No complete verified mutation set was recorded."
                        ),
                    )
                )
            elif "requested objective is implemented" in lowered:
                objective_evidence = [
                    *verified_mutations,
                    *passing_checks,
                    *passing_behavioral,
                    *approved_reviews,
                ]
                objective_satisfied = bool(verified_mutations) and bool(
                    passing_checks or passing_behavioral
                ) and bool(approved_reviews or self._is_nova_model())
                results.append(
                    CriterionResult(
                        criterion,
                        (
                            CriterionStatus.SATISFIED
                            if objective_satisfied
                            else CriterionStatus.UNVERIFIED
                        ),
                        evidence_ids=[item["id"] for item in objective_evidence],
                        detail=(
                            "Verified mutations, deterministic checks, and worker review "
                            "support the requested objective."
                            if objective_satisfied
                            else "A mutation alone is insufficient; deterministic checks "
                            "and review evidence are required."
                        ),
                    )
                )
            elif "security" in lowered or "vulnerab" in lowered:
                security_evidence = [
                    item
                    for item in passing_behavioral
                    if item.get("tool") == "security_scan"
                ] + matching_checks(criterion)
                results.append(
                    CriterionResult(
                        criterion,
                        (
                            CriterionStatus.SATISFIED
                            if security_evidence
                            else CriterionStatus.UNVERIFIED
                        ),
                        evidence_ids=[item["id"] for item in security_evidence],
                        detail=(
                            "A passing bounded security check was recorded."
                            if security_evidence
                            else "No passing security check was recorded."
                        ),
                    )
                )
            elif "verification completed" in lowered or any(
                term in lowered for term in ("test", "build", "lint", "smoke check")
            ):
                matched_checks = matching_checks(criterion)
                results.append(
                    CriterionResult(
                        criterion,
                        (
                            CriterionStatus.SATISFIED
                            if matched_checks
                            else CriterionStatus.UNVERIFIED
                        ),
                        evidence_ids=[item["id"] for item in matched_checks],
                        detail=(
                            "A matching passing project check exists."
                            if matched_checks
                            else "No matching passing project check was recorded."
                        ),
                    )
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

        event_failures = [
            item for item in (events or []) if item.get("type") == "tool_call" and not item.get("success")
        ]
        if (content or "").strip().upper().startswith("BLOCKED:"):
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

        report = self.run_ledger.finalize(
            run_status,
            objective=self._active_objective,
            criteria=results,
            files_changed=[item["filepath"] for item in changes],
            checks=checks,
            costs=self.budget.snapshot(),
            risks=risks,
            work_completed=[
                f"Updated {Path(item['filepath']).name}" for item in changes
            ],
            checks_skipped=[
                item.criterion
                for item in results
                if item.status in {
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

        return tools

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
        with tool_context(self.working_dir, self.history):
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
                evidence_id=(
                    evidence_records[-1].get("id", "") if evidence_records else ""
                ),
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
                    metadata={
                        "command": _redact_runtime_text(
                            str(args.get("command", ""))[:500]
                        )
                    },
                )
        return result, success

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
        if name in {"run_command", "run_process", "process_run"} and re.search(
            r"\b(?:curl|wget|ssh|scp|sftp|ftp|rsync|gh)\b"
            r"|\bgit\s+(?:clone|fetch|pull|push)\b"
            r"|\b(?:pip|pip3|uv)\s+(?:pip\s+)?install\b"
            r"|\b(?:npm|pnpm|yarn)\s+(?:add|install|publish)\b"
            r"|\b(?:docker|podman)\s+(?:pull|push)\b"
            r"|\bcargo\s+(?:add|install)\b|\bgo\s+get\b",
            command.lower(),
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
            scope_paths.extend(
                str(item.get("path", "")) for item in args.get("edits", [])
            )
        elif file_path:
            scope_paths.append(str(file_path))
        if name == "diff_files":
            scope_paths.extend(
                str(args.get(key, "")) for key in ("file_a", "file_b")
            )
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

        if name in self.disallowed_tools:
            return f"❌ BLOCKED: {name} is denied by the active permission rules.", False
        if self.allowed_tools and name not in self.allowed_tools:
            return f"❌ BLOCKED: {name} is not in the active tool allowlist.", False
        if self.permission_mode == "plan" and (
            name in mutation_tools
            or name in ("run_command", "run_process", "process_run")
            or name.startswith("git_")
        ):
            return "❌ BLOCKED: Plan mode is read-only. Switch permission mode before executing changes.", False

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
                        f"❌ BLOCKED: repository policy denies {policy_capability} "
                        f"for {policy_target or name}.",
                        False,
                    )
                if policy_decision == PermissionDecision.ASK and (
                    self.policy.source or extension_asked
                ):
                    approval_targets.append(policy_target or name)
            policy_requires_approval = (
                approval_targets and not _user_confirmed
            )
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
                    "⏸️ PENDING_CONFIRMATION "
                    f"[{confirmation_id}]: {policy_check.reason}. "
                    f"Enter /confirm {confirmation_id} or /cancel {confirmation_id}.",
                    False,
                )

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
            return (
                "⏸️ PENDING_CONFIRMATION "
                f"[{confirmation_id}]: {network_check.reason}. "
                f"Enter /confirm {confirmation_id} or /cancel {confirmation_id}.",
                False,
            )

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

        # Resolve scope before previews, dependency inspection, hooks, or tool
        # dispatch. This prevents an unapproved path from being read merely to
        # construct a diff.
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

        # ── Package existence gate (before dependency writes or installs) ─
        package_checks = []
        package_warning_text = ""
        if name in mutation_tools:
            for package_path, proposed_content in self._dependency_candidates(name, args):
                package_checks.extend(self.package_guard.check_file_change(package_path, proposed_content))
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
                return f"❌ BLOCKED by anti-slopsquatting guard:\n{details}", False
            unverified = [
                check for check in package_checks if check.requires_confirmation
            ]
            if unverified and not _user_confirmed:
                details = "\n".join(
                    f"  {check.registry}:{check.name} — {check.reason}"
                    for check in unverified
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
                    "⏸️ PENDING_CONFIRMATION "
                    f"[{confirmation_id}]: {uncertainty_check.reason}. "
                    "This operation was not executed. Review the exact operation, then "
                    f"enter /confirm {confirmation_id} or /cancel {confirmation_id}.\n"
                    f"{details}",
                    False,
                )
            warnings = [check for check in package_checks if check.status == "warn"]
            if warnings:
                package_warning_text = "⚠️ PACKAGE RISK WARNING:\n" + "\n".join(
                    f"  {check.registry}:{check.name} — {check.reason}" for check in warnings
                )

        # ── File diff approval gate ──────────────────────────────────────
        mutation_diff = ""
        if name in mutation_tools:
            ok, mutation_diff = preview_mutation(name, args, self.working_dir)
            if not ok:
                return f"❌ Cannot create a safe diff preview: {mutation_diff}", False
        if (
            name in mutation_tools
            and not _edit_confirmed
            and self.permission_mode != "acceptEdits"
        ):
            edit_id = self._queue_edit(name, pending_args, mutation_diff)
            return (
                f"⏸️ PENDING_EDIT [{edit_id}] — no file was changed.\n{mutation_diff}\n"
                f"Use /apply {edit_id}, /reject {edit_id}, or /edit-pending {edit_id} <replacement-file>.",
                False,
            )

        # ── 1. Determine lifecycle events ────────────────────────────────
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

        # ── 2. Fire BEFORE hooks ─────────────────────────────────────────
        if event_before:
            hook_ctx.event = event_before
            hook_results = self.hooks.fire(event_before, hook_ctx)
            if any(r.blocked for r in hook_results):
                return "❌ Operation blocked by hook policy.", False

        # ── 3. Safety check ──────────────────────────────────────────────
        safety_check = None
        if name in ("run_command", "run_process", "process_run") and command:
            safety_check = self.safety.check_command(command)
        elif name == "multi_edit":
            for edit in args.get("edits", []):
                check = self.safety.check_file_write(
                    edit.get("path", ""), edit.get("new_text", "")
                )
                if check.level in (SafetyLevel.BLOCKED, SafetyLevel.DANGEROUS):
                    safety_check = check
                    break
        elif name in mutation_tools and file_path:
            content = args.get("content", "") or args.get("new_text", "") or args.get("new_content", "")
            safety_check = self.safety.check_file_write(file_path, content)
        elif name.startswith("git_"):
            if name == "git_branch" and args.get("action") == "delete":
                safety_check = SafetyCheck(
                    level=SafetyLevel.DANGEROUS,
                    operation=f"delete git branch {args.get('name', '')}",
                    reason="Deleting a git branch may discard commits",
                    details=f"Branch: {args.get('name', '')}",
                    requires_confirmation=True,
                )
            else:
                safety_check = self.safety.check_git_operation([name] + [str(v) for v in args.values() if isinstance(v, str)])

        safety_warning = ""
        if safety_check and not safety_check.is_allowed:
            if safety_check.level == SafetyLevel.BLOCKED:
                return f"❌ BLOCKED: {safety_check.reason}", False
            if safety_check.level == SafetyLevel.DANGEROUS:
                if _user_confirmed:
                    safety_check.confirmed = True
                else:
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
            if safety_check.level == SafetyLevel.WARN:
                safety_warning = safety_check.format_warning()

        if safety_check and safety_check.level == SafetyLevel.DANGEROUS and not safety_check.is_allowed:
            return "❌ BLOCKED: Dangerous operation lacks explicit user confirmation.", False

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
                    result = (
                        extension_result
                        if isinstance(extension_result, str)
                        else json.dumps(extension_result, ensure_ascii=False)
                    )
                except Exception as exc:
                    result = f"❌ Extension tool error: {exc}"
                plugin_handled = True
                break

        if not plugin_handled:
            if self.mcp.is_mcp_tool(name):
                result = self.mcp.call_tool(name, args)
            else:
                result = execute_tool(name, args)

        if safety_check and safety_check.level == SafetyLevel.WARN:
            safety_warning = safety_check.format_warning()
            result = safety_warning + "\n" + result
        if package_warning_text:
            result = package_warning_text + "\n" + result

        success = not result.startswith(("❌", "⏰", "⏸️"))
        if name in ("api_check", "database_check", "browser_check", "security_scan"):
            try:
                success = json.loads(result).get("status") == "passed"
            except (AttributeError, TypeError, json.JSONDecodeError):
                success = False

        # ── Verified-completion evidence ─────────────────────────────────
        if success and name in mutation_tools:
            verified, detail, artifacts = verify_mutation(name, args, self.working_dir)
            code_failures = []
            if verified:
                candidate_actions = []
                raw_paths = [edit.get("path", "") for edit in args.get("edits", [])] if name == "multi_edit" else [args.get("path", "")]
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
                    detail = "compiler validation failed: " + " | ".join(check.format() for check in code_failures)
                    undo_count = len(args.get("edits", [])) if name == "multi_edit" else 1
                    rollback_ok, rollback_output = self.history.undo_changes(max(1, undo_count))
                    detail += f" | rollback={'succeeded' if rollback_ok else 'failed'}: {rollback_output}"
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
                command_exit_code(result)
                if name in ("run_command", "run_process")
                else None
            )
            status = "verified" if success and (exit_code == 0 or name == "process_run") else "failed"
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

    def _dependency_candidates(self, name: str, args: dict) -> list[tuple[str, str]]:
        """Build the exact proposed dependency-file content without writing it."""
        candidates: list[tuple[str, str]] = []
        edits = args.get("edits", []) if name == "multi_edit" else [args]
        edit_name = "edit_file" if name == "multi_edit" else name
        for edit in edits:
            raw_path = edit.get("path", "")
            if Path(raw_path).name not in {"requirements.txt", "requirements-dev.txt", "package.json", "Cargo.toml", "go.mod"}:
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
                lines[start - 1:(start - 1 if end == 0 else end)] = replacement
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
            lines.append(f"  {edit_id}: {pending['name']} {pending['args'].get('path', '(multiple files)')}")
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
            elif name in ("run_command", "run_process", "process_run"):
                cmd_val = args.get("command", "")
                if name == "run_process":
                    cmd_val = shlex.join(str(item) for item in args.get("argv", []))
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
        self._update_system_prompt()

        # ── 1. Analyze intent and activate skills ────────────────────────
        analysis = self.planner.analyze(user_input)
        plan = (
            self.planner.create_plan(user_input, analysis)
            if analysis["plan_type"] == PlanType.PLANNED
            else None
        )
        if plan:
            analysis["acceptance_criteria"] = plan.acceptance_criteria
            analysis["permitted_files"] = plan.permitted_files
            analysis["task_dag"] = [
                {
                    "id": step.id,
                    "title": step.title,
                    "depends_on": step.depends_on,
                    "risk": step.risk,
                    "retry_limit": step.retry_limit,
                }
                for step in plan.steps
            ]
        self._begin_managed_run(user_input, analysis, plan)

        if self._is_nova_model():
            content, _events = self._run_nova_turn(user_input, emit_ui=True)
            return content

        # Auto-gather context on first interaction
        context = self._gather_context()

        activated = self.skills.auto_activate(
            user_input,
            intent=analysis["intent"].value if hasattr(analysis["intent"], "value") else str(analysis["intent"]),
        )
        if activated:
            skill_names = ", ".join(s.name for s in activated)
            ui.print_info(f"Skills activated: {skill_names}")
            self._update_system_prompt()

        if self._should_use_two_node(analysis):
            content, _events = self._run_two_node_turn(user_input, analysis, emit_ui=True)
            return content

        # ── 2. Create plan if task is complex ────────────────────────────
        if plan:
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
        max_iterations = self.max_turns
        iteration = 0
        _rate_limit_retries = 0
        _max_rate_limit_retries = 3
        _key_switches = 0
        _max_key_switches = max(1, len(getattr(self.client, "nvidia_keys", [1]))) if self.client else 1

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
                self.run_ledger.append_model_call(
                    role="planner_executor",
                    model=self.model_cfg["id"],
                    status="verified",
                    usage=self.budget.snapshot().get("usage", {}),
                    detail=f"stream iteration {iteration}",
                )
                _rate_limit_retries = 0  # Reset on success
                _key_switches = 0

            except Exception as e:
                error_msg = str(e)
                if self.run_ledger.turn_dir:
                    self.run_ledger.append_model_call(
                        role="planner_executor",
                        model=self.model_cfg["id"],
                        status="failed",
                        detail=_redact_runtime_text(error_msg[:1000]),
                    )
                if isinstance(e, BudgetExceeded):
                    content = f"BLOCKED: {error_msg}"
                    self.run_ledger.append_event(
                        "budget",
                        status="blocked",
                        detail=error_msg,
                    )
                    ui.print_error(content)
                    self._finish_managed_run(content, [])
                    return content
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

                # Try switching fallback API key or provider (bounded to avoid infinite loop)
                if (is_rate_limit or is_timeout or "401" in error_msg or "Unauthorized" in error_msg or "500" in error_msg):
                    if self.client and hasattr(self.client, "switch_to_fallback") and _key_switches < _max_key_switches:
                        _key_switches += 1
                        if self.client.switch_to_fallback():
                            # Silent background rotation
                            iteration -= 1
                            continue

                # Auto-retry with exponential backoff for transient rate limits (skip if all cloud providers failed)
                if (is_rate_limit or is_timeout) and "Nexus AI Provider Failover Error" not in error_msg and _rate_limit_retries < _max_rate_limit_retries:
                    _rate_limit_retries += 1
                    wait_time = min(2 ** _rate_limit_retries, 5)
                    ui.print_warning(
                        f"API delayed/rate-limited — retrying ({_rate_limit_retries}/{_max_rate_limit_retries})..."
                    )
                    time.sleep(wait_time)
                    iteration -= 1
                    continue

                if "401" in error_msg or "Unauthorized" in error_msg:
                    ui.print_error("Invalid API key. Check your NVIDIA_API_KEY / GROQ_API_KEY.")
                elif is_rate_limit or "Nexus AI Provider Failover Error" in error_msg:
                    ui.print_warning("Cloud API rate-limited — falling back to local Nova Codex (Nova 3B v11)...")
                    if self.messages and self.messages[-1]["role"] == "user":
                        self.messages.pop()
                    content, _events = self._run_nova_turn(user_input, emit_ui=True)
                    return content
                elif "404" in error_msg:
                    ui.print_error(f"Model '{self.model_cfg['id']}' not found. Try /models to switch.")
                else:
                    ui.print_error(f"API error: {error_msg}")

                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                content = f"Error: {error_msg}"
                self.run_ledger.append_event(
                    "provider",
                    status="failed",
                    detail=error_msg,
                )
                self._finish_managed_run(content, [])
                return content

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
                content = self._guard_completion_claims(content)
                self.messages.append({"role": "assistant", "content": content})

            ui.print_response_complete()

            # ── 5. Post-plan verification ────────────────────────────────
            if plan and plan.is_complete:
                ui.print_info("📋 Plan complete. Running verification...")
                try:
                    report = self._record_verification_report(self.verifier.run_all())
                    ui.console.print(report.format_report())
                    if report.all_passed:
                        self.hooks.fire(HookEvent.ON_PLAN_COMPLETE, HookContext(event=HookEvent.ON_PLAN_COMPLETE))
                    else:
                        self.hooks.fire(HookEvent.ON_TEST_FAIL, HookContext(event=HookEvent.ON_TEST_FAIL))
                except Exception:
                    pass

            self._auto_save()
            self._finish_managed_run(content or "", [])
            return content or ""

        ui.print_warning("Reached maximum tool-call iterations (safety limit).")
        self._auto_save()
        self._finish_managed_run("", [])
        return ""

    # ── Non-Interactive Run (Web API) ────────────────────────────────────

    def run_non_interactive(self, user_input: str) -> tuple[str, list[dict]]:
        """
        Run one turn and return (final_text, all_tool_events).
        Used by the web API for structured responses.
        """
        self._load_rules_and_preferences()
        self._update_system_prompt()
        analysis_override = getattr(self, "_resume_analysis_override", None)
        plan_override = getattr(self, "_resume_plan_override", None)
        analysis = analysis_override or self.planner.analyze(user_input)
        plan = plan_override or (
            self.planner.create_plan(user_input, analysis)
            if analysis["plan_type"] == PlanType.PLANNED
            else None
        )
        self._resume_analysis_override = None
        self._resume_plan_override = None
        if plan:
            analysis["acceptance_criteria"] = plan.acceptance_criteria
            analysis["permitted_files"] = plan.permitted_files
            analysis["task_dag"] = [
                {
                    "id": step.id,
                    "title": step.title,
                    "depends_on": step.depends_on,
                    "risk": step.risk,
                    "retry_limit": step.retry_limit,
                }
                for step in plan.steps
            ]
        self._begin_managed_run(user_input, analysis, plan)
        if self._is_nova_model():
            return self._run_nova_turn(user_input, emit_ui=False)

        events: list[dict] = []

        # Auto-gather context
        context = self._gather_context()
        if context:
            augmented_input = context + "User request: " + user_input
        else:
            augmented_input = user_input

        # Auto-activate skills
        try:
            self.skills.auto_activate(
                user_input,
                intent=analysis["intent"].value if hasattr(analysis["intent"], "value") else str(analysis["intent"]),
            )
            self._update_system_prompt()
            if self._should_use_two_node(analysis):
                return self._run_two_node_turn(user_input, analysis, emit_ui=False)
        except Exception:
            pass

        self.messages.append({"role": "user", "content": augmented_input})

        max_iterations = self.max_turns
        iteration = 0
        final_content = ""
        _non_int_key_switches = 0
        _max_non_int_switches = max(1, len(getattr(self.client, "nvidia_keys", [1]))) if self.client else 1

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
                self.run_ledger.append_model_call(
                    role="planner_executor",
                    model=self.model_cfg["id"],
                    status="verified",
                    usage={
                        "prompt_tokens": int(
                            getattr(getattr(response, "usage", None), "prompt_tokens", 0)
                            or 0
                        ),
                        "completion_tokens": int(
                            getattr(
                                getattr(response, "usage", None),
                                "completion_tokens",
                                0,
                            )
                            or 0
                        ),
                    },
                    detail=f"headless iteration {iteration}",
                )

            except Exception as e:
                error_msg = str(e)
                if self.run_ledger.turn_dir:
                    self.run_ledger.append_model_call(
                        role="planner_executor",
                        model=self.model_cfg["id"],
                        status="failed",
                        detail=_redact_runtime_text(error_msg[:1000]),
                    )
                if isinstance(e, BudgetExceeded):
                    content = f"BLOCKED: {error_msg}"
                    self.run_ledger.append_event(
                        "budget",
                        status="blocked",
                        detail=error_msg,
                    )
                    self._finish_managed_run(content, events)
                    return content, events
                if ("401" in error_msg or "429" in error_msg or "Unauthorized" in error_msg or "rate" in error_msg.lower()):
                    if self.client and hasattr(self.client, "switch_to_fallback") and _non_int_key_switches < _max_non_int_switches:
                        _non_int_key_switches += 1
                        if self.client.switch_to_fallback():
                            iteration -= 1
                            continue
                if self.messages and self.messages[-1]["role"] == "user":
                    self.messages.pop()
                content = f"Error: {error_msg}"
                self._finish_managed_run(content, events)
                return content, events

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
                content = self._guard_completion_claims(content)
                self.messages.append({"role": "assistant", "content": content})

            final_content = content
            self._auto_save()
            break

        self._finish_managed_run(final_content, events)
        return final_content, events

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
        expected_workspace = Path(
            request_record.get("working_dir") or self.working_dir
        ).expanduser().resolve()
        if expected_workspace != Path(self.working_dir).resolve():
            raise ValueError(
                "Resume workspace mismatch: "
                f"expected {expected_workspace}, got {self.working_dir}"
            )
        plan_data = inspected.get("plan", {})
        if not plan_data.get("id"):
            raise ValueError("Interrupted run has no resumable execution plan")
        plan = ExecutionPlan.from_dict(plan_data)
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
        completed = [
            step.id for step in plan.steps if step.status == TaskStatus.COMPLETED
        ]
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

    def _run_two_node_turn(self, user_input: str, analysis: dict, emit_ui: bool = True) -> tuple[str, list[dict]]:
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
                live.start("Ceiling planning; Nova Intern standing by...")
                try:
                    result = backend.run(user_input, planner_analysis=analysis)
                finally:
                    live.stop()
            else:
                result = backend.run(user_input, planner_analysis=analysis)
        except Exception as e:
            if emit_ui:
                ui.print_warning(f"Two-node backend error ({e}) — falling back to local Nova Codex...")
            if self.messages and self.messages[-1]["role"] == "user":
                self.messages.pop()
            return self._run_nova_turn(user_input, emit_ui=emit_ui)

        def record_result(candidate, phase: str) -> None:
            if candidate.execution_plan is not None:
                self._active_plan = candidate.execution_plan
                self.planner.current_plan = candidate.execution_plan
            self.run_ledger.append_model_call(
                role=f"ceiling_{phase}",
                model=self.model_cfg["id"],
                status=(
                    "verified"
                    if candidate.review_approved
                    else "failed"
                ),
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
                        execution.guardrail_log
                        + "\n\n[RAW MODEL OUTPUT]\n"
                        + execution.raw_output
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
                key: value
                for key, value in analysis.items()
                if key != "resume_plan"
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
            event.get("success", False)
            for event in events
            if event.get("type") == "tool_call"
        )
        recovered_without_edits = bool(
            result.review_approved
            and not result.proposals
            and result.execution_plan is not None
            and result.execution_plan.steps
            and all(
                step.status == TaskStatus.COMPLETED
                for step in result.execution_plan.steps
            )
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
                    key: value
                    for key, value in analysis.items()
                    if key != "resume_plan"
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
        self._finish_managed_run(breakdown, events)
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
            self.messages.append({"role": "assistant", "content": content})
            self._auto_save()
            self._finish_managed_run(content, events)
            return content, events
        except Exception as e:
            content = f"Nova backend error: {e}"
            if emit_ui:
                ui.print_error(content)
            self.messages.append({"role": "assistant", "content": content})
            self._auto_save()
            self._finish_managed_run(content, events)
            return content, events

        if emit_ui and nova_result.raw_output:
            ui.console.print(nova_result.raw_output)
        if emit_ui and nova_result.guardrail_output:
            ui.print_info("Nova guardrail verdicts:")
            ui.console.print(nova_result.guardrail_output)

        # Structured/headless callers receive the same complete model and
        # guardrail transcript that interactive users see.  This is evidence,
        # not a shortened summary, so rejected generations remain auditable.
        events.append({
            "type": "model_trace",
            "node": "nova",
            "raw_output": nova_result.raw_output,
            "guardrail_output": nova_result.guardrail_output,
        })

        mutated = False
        for proposal in nova_result.proposals:
            args = dict(proposal.args)
            display_args = {k: v for k, v in args.items() if k != "_nova_guardrail"}
            if emit_ui:
                ui.print_tool_call(proposal.name, display_args)
            result, success = self._execute_tool_with_safety(proposal.name, args)
            if emit_ui:
                ui.print_tool_result(result, success)
            events.append({
                "type": "tool_call",
                "name": proposal.name,
                "args": display_args,
                "result": result,
                "success": success,
                "nova_guardrail": proposal.guardrail_summary,
            })
            if success and proposal.name in {"replace_file_content", "multi_replace_file_content", "write_to_file", "run_command"}:
                mutated = True

        if mutated:
            report = self.run_verification()
            if emit_ui:
                ui.console.print(report)

        final_content = self._guard_completion_claims(nova_result.assistant_text)
        if emit_ui:
            ui.print_response_complete()
        self.messages.append({"role": "assistant", "content": final_content})
        self._auto_save()
        self._finish_managed_run(final_content, events)
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

        self.hooks.fire(HookEvent.ON_SUBAGENT_COMPLETE, HookContext(
            event=HookEvent.ON_SUBAGENT_COMPLETE,
            metadata={"subagent": template_name, "task": task},
        ))

        return result.format_report()

    def run_verification(self, checks: list[str] | None = None) -> str:
        """Run verification checks and return the report."""
        check_types = None
        if checks:
            valid = {item.value for item in CheckType}
            check_types = [CheckType(c) for c in checks if c in valid]
        report = self._record_verification_report(self.verifier.run_all(check_types))
        return report.format_report()

    def _record_verification_report(self, report):
        """Mirror deterministic project checks into the evidence trail."""
        for index, check in enumerate(report.checks, 1):
            status = "verified" if check.passed else "failed"
            exit_code = 0 if check.passed else 1
            self.evidence.append(
                kind="command",
                claim=f"project verification: {check.check_type.value}",
                status=status,
                tool="verification_engine",
                command=check.command,
                exit_code=exit_code,
                raw_output=check.output,
                metadata={
                    "duration_ms": check.duration_ms,
                    "check_status": check.status.value,
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
            "test", "pytest", "jest", "vitest", "ruff", "mypy", "tsc", "lint",
            "build", "compile", "cargo check", "go vet", "node --check",
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
        claims_tests = bool(re.search(r"\b(tests?|checks?|build)\b.{0,30}\b(pass(?:ed|ing)?|green|success)", content, re.I))
        if claims_tests:
            has_test_evidence = any(
                record.get("kind") == "command"
                and record.get("status") == "verified"
                and record.get("exit_code") == 0
                and any(term in record.get("command", "").lower() for term in ("test", "pytest", "jest", "build", "check"))
                for record in records
            )
            if not has_test_evidence:
                warnings.append("UNVERIFIED TEST CLAIM: no real passing test/build command was recorded this turn.")
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
