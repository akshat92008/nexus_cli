"""
ToolExecutionController — extracted service for tool safety dispatch.

This module provides a typed interface that formalises the tool-execution
pipeline.  The Agent class delegates its ``_execute_tool_with_safety`` method
to this controller so the ~425-line implementation lives in one responsible
class rather than buried inside the monolithic Agent.

Usage::

    from nexus.tool_executor import ToolExecutionController
    # The Agent passes ``self`` as the host; the controller accesses agent
    # attributes through the declared protocol interface.
    ctrl = ToolExecutionController(agent)
    result, ok = ctrl.execute("write_file", {"path": "a.py", "content": "..."})

Architecture::

    ToolExecutionController
    ├── _check_capability()          reject unknown / blocked tools early
    ├── _apply_network_tag()         mark network-touching commands
    ├── _run_before_hooks()          pre-execution hook chain
    ├── _dispatch()                  route to execute_tool()
    ├── _record_evidence()           append to EvidenceTrail
    ├── _run_after_hooks()           post-execution hook chain
    └── _maybe_reflect()            optional ReflectionEngine call
"""

from __future__ import annotations

import json
import logging
import re
import shlex
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Protocol


from nexus.approvals import preview_mutation
from nexus.capabilities import ToolCapability
from nexus.code_validation import GeneratedCodeValidator
from nexus.evidence import command_exit_code, verify_mutation
from nexus.extensions import ToolContext
from nexus.hooks.base import HookContext, HookEvent
from nexus.planner import TaskStatus
from nexus.policy import PermissionDecision
from nexus.safety import SafetyCheck, SafetyLevel
from nexus.tools import execute_tool

if TYPE_CHECKING:
    from nexus.agent import Agent

logger = logging.getLogger(__name__)


class AgentProtocol(Protocol):
    """Minimal interface the controller needs from the Agent."""

    working_dir: str
    mode_policy: Any
    evidence: Any
    hooks: Any
    reflection: Any
    _tool_capabilities: dict[str, Any]
    _pending_confirmations: dict[str, Any]

    def _queue_confirmation(
        self,
        *,
        name: str,
        args: dict,
        safety_check: Any,
        edit_confirmed: bool,
    ) -> str: ...

    def execute_tool_raw(self, name: str, args: dict) -> tuple[str, bool]: ...


class ToolExecutionController:
    """
    Typed service that owns the tool safety → dispatch → evidence pipeline.

    This is a *delegation target* for ``Agent._execute_tool_with_safety``.
    It does not replace the agent but reduces the agent's responsibility
    surface by centralising tool-lifecycle logic here.

    Thread safety: each agent call is single-threaded; no locking needed here.
    """

    # Commands that require network access — auto-tagged by the controller.
    _NETWORK_COMMAND_PATTERN = re.compile(
        r"\b(?:curl|wget|ssh|scp|sftp|ftp|rsync|gh)\b"
        r"|\bgit\s+(?:clone|fetch|pull|push)\b"
        r"|\b(?:pip|pip3|uv)\s+(?:pip\s+)?install\b"
        r"|\b(?:npm|pnpm|yarn)\s+(?:add|install|publish)\b"
        r"|\b(?:docker|podman)\s+(?:pull|push)\b"
        r"|\bcargo\s+(?:add|install)\b|\bgo\s+get\b",
        re.IGNORECASE,
    )

    # Tools that read files or the repo index (no mutation).
    _READ_TOOLS: frozenset[str] = frozenset(
        {
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
    )

    # Tools that mutate files on disk.
    _MUTATION_TOOLS: tuple[str, ...] = ("write_file", "edit_file", "patch_file", "multi_edit")

    def __init__(self, agent: "Agent") -> None:
        self._agent = agent

    # ──────────────────────────────────────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────────────────────────────────────

    def execute(
        self,
        name: str,
        args: dict,
        *,
        _user_initiated: bool = False,
        _user_confirmed: bool = False,
        _edit_confirmed: bool = False,
    ) -> tuple[str, bool]:
        """Execute a guarded tool and mirror its outcome into the run ledger."""
        started = time.monotonic()
        from nexus.run_context import run_context_scope
        from nexus.tools import tool_context

        with run_context_scope(self._agent.run_context), tool_context(
            self._agent.working_dir, self._agent.history, self._agent.conversation_id
        ):
            result, success = self._execute_impl(
                name,
                args,
                _user_initiated=_user_initiated,
                _user_confirmed=_user_confirmed,
                _edit_confirmed=_edit_confirmed,
            )
        if _user_confirmed:
            self._agent._permissions_used.add(f"{name}: explicit approval")
        if success and name in {"web_fetch", "web_search", "api_check", "browser_check"}:
            target = str(args.get("url") or args.get("query") or "")
            self._agent._network_calls.append(f"{name}: {target}")
        elif success and args.get("network"):
            target = str(args.get("command") or args.get("argv") or name)
            self._agent._network_calls.append(f"{name}: {target}")
        run_ledger = getattr(self._agent, "run_ledger", None)
        if run_ledger and run_ledger.turn_dir:
            from nexus.agent import _redact_runtime_text
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
            self._agent.run_ledger.append_event(
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
            evidence_records = self._agent.evidence.records(limit=1)
            self._agent.run_ledger.append_tool_call(
                tool=name,
                status="verified" if success else "failed",
                arguments=safe_args,
                evidence_id=(evidence_records[-1].get("id", "") if evidence_records else ""),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            self._agent.run_ledger.record_costs(self._agent.budget.snapshot())
            mutation_tools = {"write_file", "edit_file", "patch_file", "multi_edit"}
            if success and name in mutation_tools:
                raw_paths = (
                    [item.get("path", "") for item in args.get("edits", [])]
                    if name == "multi_edit"
                    else [args.get("path", "")]
                )
                try:
                    self._agent.repo_graph.update_paths(path for path in raw_paths if path)
                except (OSError, ValueError) as exc:
                    logger.debug("Repository graph incremental refresh failed: %s", exc)
                self._agent.run_ledger.checkpoint(
                    f"verified-{name}",
                    plan=self._agent._active_plan,
                    evidence_count=len(self._agent.evidence.records()),
                    history_count=len(self._agent.history.changes),
                    metadata={"paths": [path for path in raw_paths if path]},
                )
            elif success and name in ("run_command", "run_process"):
                self._agent.run_ledger.checkpoint(
                    "command-completed",
                    plan=self._agent._active_plan,
                    evidence_count=len(self._agent.evidence.records()),
                    history_count=len(self._agent.history.changes),
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
        _user_initiated: bool,
        _user_confirmed: bool,
        _edit_confirmed: bool,
        mutation_tools: tuple,
        read_tools: set,
    ) -> tuple[bool, str, tuple[str, bool]]:
        if name in self._agent.disallowed_tools:
            return (
                False,
                "",
                (f"❌ BLOCKED: {name} is denied by the active permission rules.", False),
            )
        if self._agent.allowed_tools and name not in self._agent.allowed_tools:
            return False, "", (f"❌ BLOCKED: {name} is not in the active tool allowlist.", False)
        if self._agent._active_plan is not None and self._agent._enforce_plan_tool_contract:
            current = next(
                (step for step in self._agent._active_plan.steps if step.status == TaskStatus.IN_PROGRESS),
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
        if not self._agent.mode_policy.may_edit and not _user_initiated and (
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
                policy_decision = self._agent.policy.decide(
                    policy_capability,
                    policy_target,
                )
                extension_asked = False
                for provider in self._agent.extensions.loaded("policies"):
                    external = str(
                        provider.decide(
                            policy_capability,
                            policy_target,
                            ToolContext(
                                working_dir=self._agent.working_dir,
                                session_id=self._agent.conversation_id,
                                permission_mode=self._agent.permission_mode,
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
                    self._agent.policy.source
                    or extension_asked
                    or (
                        self._agent.mode_policy.require_review
                        and policy_capability
                        in {"command", "package_install", "deployment", "git_push"}
                    )
                ):
                    approval_targets.append(policy_target or name)
            policy_requires_approval = approval_targets and not (_user_confirmed or _user_initiated)
            if policy_requires_approval:
                policy_target = ", ".join(approval_targets)
                policy_check = SafetyCheck(
                    level=SafetyLevel.DANGEROUS,
                    operation=f"{policy_capability}: {policy_target or name}",
                    reason=f"Repository policy requires approval for {policy_capability}",
                    details=policy_target or name,
                    requires_confirmation=True,
                )
                confirmation_id = self._agent._queue_confirmation(
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
                        "This operation was not executed. "
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
        _user_initiated: bool,
        _user_confirmed: bool,
        _edit_confirmed: bool,
    ) -> tuple[bool, tuple[str, bool]]:
        requests_network = bool(args.get("network")) or bool(args.get("allow_external"))
        if requests_network and not (_user_confirmed or _user_initiated):
            network_check = SafetyCheck(
                level=SafetyLevel.DANGEROUS,
                operation=f"{name} network access",
                reason="Network access is disabled by default",
                details=command or str(args.get("url", "")),
                requires_confirmation=True,
            )
            confirmation_id = self._agent._queue_confirmation(
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
            for package_path, proposed_content in self._agent._dependency_candidates(name, args):
                try:
                    current_content = Path(package_path).read_text(encoding="utf-8")
                except OSError:
                    current_content = ""
                package_checks.extend(
                    self._agent.package_guard.check_file_change(
                        package_path,
                        proposed_content,
                        current_content=current_content,
                    )
                )
        elif name in ("run_command", "run_process", "process_run") and command:
            package_checks = self._agent.package_guard.check_command(command)
        if package_checks:
            for check in package_checks:
                self._agent.evidence.append(
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
                confirmation_id = self._agent._queue_confirmation(
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
            ok, mutation_diff = preview_mutation(name, args, self._agent.working_dir)
            if not ok:
                return False, "", (f"❌ Cannot create a safe diff preview: {mutation_diff}", False)
            if self._agent.mode_policy.require_review and not _edit_confirmed:
                confirmation_id = self._agent._queue_edit(name, pending_args, mutation_diff)
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
        for plugin in self._agent.plugin_loader.plugins.values():
            dispatch = plugin.get_tool_dispatch()
            if name in dispatch:
                try:
                    return dispatch[name](**args)
                except LookupError as e:
                    return f"❌ Plugin tool error: {e}"

        for extension_tool in self._agent.extensions.loaded("tools"):
            if extension_tool.name != name:
                continue
            try:
                extension_result = extension_tool.invoke(
                    args,
                    ToolContext(
                        working_dir=self._agent.working_dir,
                        session_id=self._agent.conversation_id,
                        task_id=(
                            str(self._agent._active_plan.current_step)
                            if self._agent._active_plan is not None
                            else ""
                        ),
                        permission_mode=self._agent.permission_mode,
                    ),
                )
                return (
                    extension_result
                    if isinstance(extension_result, str)
                    else json.dumps(extension_result, ensure_ascii=False)
                )
            except (TypeError, ValueError) as exc:
                return f"❌ Extension tool error: {exc}"

        if self._agent.mcp.is_mcp_tool(name):
            return self._agent.mcp.call_tool(name, args)
        else:
            return execute_tool(name, args)
    def _snapshot_workspace(self) -> dict[str, float]:
        """Snapshot the actual workspace before execution."""
        snapshot = {}
        ignored = {".git", ".nexusai", "node_modules", "venv", ".venv", "__pycache__", "history", ".pytest_cache"}
        wd = Path(self._agent.working_dir)
        try:
            for path in wd.rglob("*"):
                if path.is_file() and not any(part in ignored for part in path.parts):
                    snapshot[str(path)] = path.stat().st_mtime
        except OSError:
            pass
        return snapshot

    def _reconcile_workspace(self, before_snapshot: dict[str, float], after_snapshot: dict[str, float]) -> list[str]:
        """Reconcile filesystem/Git changes after a potentially mutating command."""
        changed = []
        for path, mtime in after_snapshot.items():
            if path not in before_snapshot or before_snapshot[path] != mtime:
                changed.append(path)
        return changed

    def _execute_impl(
        self,
        name: str,
        args: dict,
        *,
        _user_initiated: bool = False,
        _user_confirmed: bool = False,
        _edit_confirmed: bool = False,
    ) -> tuple[str, bool]:
        """
        Execute a tool with full safety checks, hooks, and context tracking.

        Pipeline: Before Hooks → Safety Check → Execute → Context Track → After Hooks → Reflection
        """
        from nexus.tools import normalize_tool_arguments
        from nexus.agent import _is_relative_to, _redact_runtime_text

        args = normalize_tool_arguments(name, args)
        declaration = self._agent._tool_capabilities.get(name)
        if declaration is None:
            return f"❌ BLOCKED: Tool '{name}' has no capability declaration.", False
        if (
            declaration.requires(ToolCapability.CONFIRMATION_REQUIRED)
            and not _user_confirmed
        ):
            capability_check = SafetyCheck(
                level=SafetyLevel.DANGEROUS,
                operation=f"external tool: {name}",
                reason="This tool declares external side effects and requires approval",
                details=json.dumps(args, ensure_ascii=False, default=str)[:2000],
                requires_confirmation=True,
            )
            confirmation_id = self._agent._queue_confirmation(
                name=name,
                args=args,
                safety_check=capability_check,
                edit_confirmed=_edit_confirmed,
            )
            return (
                "⏸️ PENDING_CONFIRMATION "
                f"[{confirmation_id}]: {capability_check.reason}. "
                f"Enter /confirm {confirmation_id} or /cancel {confirmation_id}.",
                False,
            )
        if name == "run_command" and not self._agent.mode_policy.allow_shell_command:
            return (
                "❌ BLOCKED: shell-string execution is disabled in this mode; use "
                "run_process with an explicit argv array.",
                False,
            )
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
        for argument_name in self._agent._external_tool_path_arguments.get(name, ()):
            value = args.get(argument_name)
            if isinstance(value, (list, tuple, set)):
                scope_paths.extend(str(item) for item in value)
            elif value not in (None, ""):
                scope_paths.append(str(value))
        scope_paths = list(dict.fromkeys(item for item in scope_paths if item))

        # ── 1. Enforce Tool Policy
        ok, policy_capability, err_res = self._enforce_tool_policy(
            name,
            args,
            command,
            scope_paths,
            pending_args,
            _user_initiated,
            _user_confirmed,
            _edit_confirmed,
            mutation_tools,
            read_tools,
        )
        if not ok:
            return err_res

        # ── 2. Enforce Network Safety
        ok, err_res = self._enforce_network_safety(
            name, args, command, pending_args, _user_initiated, _user_confirmed, _edit_confirmed
        )
        if not ok:
            return err_res

        # Nova Guardrail checks for mutations
        if name in mutation_tools:
            if nova_guardrail is not None and not nova_guardrail.get("passed"):
                return "❌ BLOCKED: Nova guardrail metadata was present but did not pass.", False
            if self._agent._is_nova_model() and (not nova_guardrail or not nova_guardrail.get("passed")):
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
                early_check = self._agent.safety.check_file_write(early_path, early_content)
                if early_check.level == SafetyLevel.BLOCKED:
                    return f"❌ BLOCKED: {early_check.reason}", False

        # Resolve scope outside workspace
        for scoped_path in (item for item in scope_paths if item):
            resolved_file = Path(scoped_path).expanduser()
            if not resolved_file.is_absolute():
                resolved_file = Path(self._agent.working_dir) / resolved_file
            resolved_file = resolved_file.resolve()
            roots = [Path(self._agent.working_dir), *(Path(item) for item in self._agent.additional_dirs)]
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
                confirmation_id = self._agent._queue_confirmation(
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
            hook_results = self._agent.hooks.fire(event_before, hook_ctx)
            if any(r.blocked for r in hook_results):
                return "❌ Operation blocked by hook policy.", False

        # ── Safety check ──
        safety_check = None
        if name in ("run_command", "run_process", "process_run") and command:
            safety_check = self._agent.safety.check_command(command)
        elif name == "multi_edit":
            for edit in args.get("edits", []):
                check = self._agent.safety.check_file_write(edit.get("path", ""), edit.get("new_text", ""))
                if check.level in (SafetyLevel.BLOCKED, SafetyLevel.DANGEROUS):
                    safety_check = check
                    break
        elif name in mutation_tools and file_path:
            content_val = (
                args.get("content", "") or args.get("new_text", "") or args.get("new_content", "")
            )
            safety_check = self._agent.safety.check_file_write(file_path, content_val)

        if safety_check and safety_check.level == SafetyLevel.BLOCKED:
            return f"❌ BLOCKED: {safety_check.reason}", False
        elif safety_check and safety_check.level == SafetyLevel.DANGEROUS and not _user_confirmed:
            confirmation_id = self._agent._queue_confirmation(
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
        # Production presets fail closed for every command when no kernel-backed
        # workspace boundary is available. A merely "safe-looking" command can
        # still read arbitrary host paths, so danger classification is not a
        # containment boundary.
        if (
            name in ("run_command", "run_process", "process_run")
            and self._agent.mode_policy.require_os_isolation
        ):
            args["require_os_isolation"] = True

        # ── 5. Execute
        before_snapshot = None
        if name in ("run_command", "run_process", "process_run"):
            before_snapshot = self._snapshot_workspace()
    
        result = self._dispatch_tool_execution(name, args)

        success = not result.output.startswith(("❌", "⏰", "⏸️"))
        if name in ("api_check", "database_check", "browser_check", "security_scan"):
            try:
                success = json.loads(result.output).get("status") == "passed"
            except (AttributeError, TypeError, json.JSONDecodeError):
                success = False

        if package_warning_text:
            result.output = package_warning_text + "\n" + result.output

        # Reconcile filesystem changes for shell commands
        if success and name in ("run_command", "run_process", "process_run") and before_snapshot is not None:
            after_snapshot = self._snapshot_workspace()
            mutations = self._reconcile_workspace(before_snapshot, after_snapshot)
            for mutated_file in mutations:
                self._agent.history.record_change(mutated_file, name, None, f"Mutated implicitly by {name}")
                verif, det, arts = verify_mutation("edit_file", {"path": mutated_file}, self._agent.working_dir)
                self._agent.evidence.append(
                    kind="file_mutation",
                    claim=f"undeclared mutation detected by {name} in {mutated_file}",
                    status="verified" if verif else "failed",
                    tool=name,
                    artifacts=arts,
                    raw_output="",
                    metadata={"verification": det},
                )

        # ── Verified-completion evidence
        if success and name in mutation_tools:
            verified, detail, artifacts = verify_mutation(name, args, self._agent.working_dir)
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
                        from nexus.agent import _is_relative_to
                        path_obj = Path(raw_path).expanduser()
                        if not path_obj.is_absolute():
                            path_obj = Path(self._agent.working_dir) / path_obj
                        if path_obj.is_absolute() and not _is_relative_to(
                            path_obj, Path(self._agent.working_dir)
                        ):
                            continue
                        relative = path_obj.resolve().relative_to(Path(self._agent.working_dir))
                        candidate_actions.append(SimpleNamespace(path=str(relative)))
                    except ValueError:
                        continue
                code_checks = GeneratedCodeValidator(self._agent.working_dir).validate(candidate_actions)
                code_failures = [check for check in code_checks if not check.passed]
                if code_failures:
                    verified = False
                    detail = "compiler validation failed: " + " | ".join(
                        check.format() for check in code_failures
                    )
                    undo_count = len(args.get("edits", [])) if name == "multi_edit" else 1
                    rollback_ok, rollback_output = self._agent.history.undo_changes(max(1, undo_count))
                    detail += (
                        f" | rollback={'succeeded' if rollback_ok else 'failed'}: {rollback_output}"
                    )
            if code_checks:
                self._agent.evidence.append(
                    kind="verification_check",
                    claim="generated code compiler and syntax validation",
                    status="verified" if not code_failures else "failed",
                    tool="generated_code_validator",
                    command="generated-code-validator",
                    exit_code=0 if not code_failures else 1,
                    raw_output="\n".join(check.format() for check in code_checks),
                    metadata={"check_type": "syntax"},
                )
            self._agent.evidence.append(
                kind="file_mutation",
                claim=f"{name} persisted the requested change",
                status="verified" if verified else "failed",
                tool=name,
                artifacts=artifacts,
                raw_output=result.output,
                metadata={"verification": detail},
            )
            if not verified:
                return f"❌ WRITE VERIFICATION FAILED: {detail}\nRaw tool output:\n{result.output}", False
            if self._agent.run_ledger.turn_dir and mutation_diff:
                self._agent.run_ledger.store_artifact(
                    "patches",
                    f"{name}-{len(self._agent.history.changes):04d}.diff",
                    mutation_diff,
                )
            result.output += f"\n🔎 VERIFIED: {detail}\nEvidence: {self._agent.evidence.path}"
        elif name in ("run_command", "run_process", "process_run"):
            exit_code = (
                command_exit_code(result.output) if name in ("run_command", "run_process") else None
            )
            status = (
                "verified" if success and (exit_code == 0 or name == "process_run") else "failed"
            )
            self._agent.evidence.append(
                kind="command",
                claim=f"executed command: {command}",
                status=status,
                tool=name,
                command=command,
                exit_code=exit_code,
                raw_output=result.output,
            )
        elif name in ("api_check", "database_check", "browser_check", "security_scan"):
            probe_status = ""
            try:
                probe_status = str(json.loads(result.output).get("status", ""))
            except (TypeError, json.JSONDecodeError):
                pass
            self._agent.evidence.append(
                kind="behavioral_verification",
                claim=f"executed {name}",
                status="verified" if success and probe_status == "passed" else "failed",
                tool=name,
                raw_output=result.output,
                metadata={"probe_status": probe_status},
            )
        elif name.startswith("git_"):
            self._agent.evidence.append(
                kind="git_operation",
                claim=f"executed {name}",
                status="verified" if success else "failed",
                tool=name,
                raw_output=result.output,
                metadata={"arguments": args},
            )

        # ── 6. Track file access in context manager
        if file_path:
            was_edited = name in ("write_file", "edit_file", "patch_file", "multi_edit")
            self._agent.context_mgr.track_file_access(file_path, was_edited=was_edited)
            if success and name == "read_file" and result:
                self._agent.context_mgr.track_file_imports(file_path, result.output)
                self._agent.context_mgr.summarize_file(file_path, result.output)

        # ── 7. Fire AFTER hooks
        if event_after:
            hook_ctx.event = event_after
            hook_ctx.tool_result = result.output
            self._agent.hooks.fire(event_after, hook_ctx)

        # ── 8. Fire error hook on failure
        if not success:
            self._agent.hooks.fire(
                HookEvent.ON_ERROR,
                HookContext(
                    event=HookEvent.ON_ERROR,
                    error_message=result.output[:500],
                    tool_name=name,
                    tool_args=args,
                ),
            )

        return result.output, success


    # ──────────────────────────────────────────────────────────────────────────
    # Introspection helpers (used by tests and the dashboard)
    # ──────────────────────────────────────────────────────────────────────────

    def is_mutation_tool(self, name: str) -> bool:
        """Return True if *name* modifies files on disk."""
        return name in self._MUTATION_TOOLS

    def is_read_tool(self, name: str) -> bool:
        """Return True if *name* is a read-only operation."""
        return name in self._READ_TOOLS

    def needs_network_tag(self, command: str) -> bool:
        """Return True if *command* string implies external network access."""
        return bool(self._NETWORK_COMMAND_PATTERN.search(command))

    def describe_pipeline(self) -> dict[str, list[str]]:
        """Return a machine-readable description of the execution pipeline stages."""
        return {
            "stages": [
                "capability_check",
                "confirmation_gate",
                "shell_command_policy",
                "network_tag",
                "scope_path_resolution",
                "before_hooks",
                "safety_layer",
                "execute_tool",
                "evidence_record",
                "after_hooks",
                "reflection",
            ],
            "mutation_tools": list(self._MUTATION_TOOLS),
            "read_tools": sorted(self._READ_TOOLS),
        }


# ─── Convenience factory ─────────────────────────────────────────────────────


def make_controller(agent: "Agent") -> ToolExecutionController:
    """Create and attach a ``ToolExecutionController`` to *agent*."""
    ctrl = ToolExecutionController(agent)
    agent._tool_controller = ctrl  # type: ignore[attr-defined]
    return ctrl
