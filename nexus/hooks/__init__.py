"""
Hooks Engine — lifecycle automation that triggers actions on events.

Events: file edit, command run, commit, push, error, plan complete, etc.
Hook types: shell commands, prompt injections, tool calls, MCP calls.
"""

from nexus.hooks.base import BaseHook, HookEvent, HookType
from nexus.hooks.runner import HookRunner

__all__ = ["HookEvent", "HookType", "BaseHook", "HookRunner"]
