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
from typing import TYPE_CHECKING, Any, Protocol

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
        args: dict[str, Any],
        *,
        user_initiated: bool = False,
        user_confirmed: bool = False,
        edit_confirmed: bool = False,
    ) -> tuple[str, bool]:
        """
        Full tool-execution pipeline with safety, hooks, evidence, and reflection.

        Returns ``(output_text, success_bool)``.
        """
        # Delegate back to the agent's existing implementation for now.
        # This wrapper exists as the *future* extraction point so callers
        # can be migrated one by one without a big-bang refactor.
        return self._agent._execute_tool_with_safety(
            name,
            args,
            _user_initiated=user_initiated,
            _user_confirmed=user_confirmed,
            _edit_confirmed=edit_confirmed,
        )

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
