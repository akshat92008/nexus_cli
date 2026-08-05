import atexit
import contextvars
import fnmatch
import hashlib
import html
import http.client
import json
import mimetypes
import os
import re
import shlex
import signal
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from nexus.paths import nexus_home
from dataclasses import dataclass, field
from typing import Any, Callable
from enum import Enum

def tool_context(working_dir: str, history=None, owner: str = ""):
    token_dir = _tool_working_dir.set(str(working_dir))
    token_owner = _tool_owner.set(owner)
    token_hist = None
    if history is not None:
        token_hist = _tool_history.set(history)
    try:
        yield
    finally:
        _tool_working_dir.reset(token_dir)
        _tool_owner.reset(token_owner)
        if token_hist is not None:
            _tool_history.reset(token_hist)

def get_history():
    history = _tool_history.get()
    if history is None:
        from nexus.history import FileHistory

        return FileHistory()
    return history

def normalize_tool_arguments(name: str, args: dict) -> dict:
    """Normalize common tool parameter name variations from LLMs."""
    args = dict(args)
    if name in ("read_file", "write_file", "edit_file", "patch_file", "file_info"):
        if "path" not in args:
            for alt in ("file_path", "file", "filename", "filepath", "target_file"):
                if alt in args:
                    args["path"] = args.pop(alt)
                    break
        if "path" in args and isinstance(args["path"], str):
            p = args["path"]
            import getpass

            curr_user = getpass.getuser()
            p = re.sub(
                r"^/Users/\[?(?:username|user|yourname|name)\]?/",
                f"/Users/{curr_user}/",
                p,
                flags=re.I,
            )
            p = re.sub(
                r"^/home/\[?(?:username|user|yourname|name)\]?/",
                f"/home/{curr_user}/",
                p,
                flags=re.I,
            )
            args["path"] = p
    elif name in ("run_command", "process_run"):
        if "command" not in args:
            for alt in ("cmd", "shell_command", "script", "exec"):
                if alt in args:
                    args["command"] = args.pop(alt)
                    break
    elif name == "run_process":
        if "argv" not in args:
            for alt in ("args", "command", "cmd"):
                if alt in args:
                    value = args.pop(alt)
                    args["argv"] = value if isinstance(value, list) else [str(value)]
                    break
    elif name == "search_code":
        if "pattern" not in args:
            for alt in ("query", "search_pattern", "regex", "term"):
                if alt in args:
                    args["pattern"] = args.pop(alt)
                    break
    elif name == "web_fetch":
        if "url" not in args:
            for alt in ("link", "uri", "target_url"):
                if alt in args:
                    args["url"] = args.pop(alt)
                    break
    elif name == "web_search":
        if "query" not in args:
            for alt in ("q", "search", "term", "keywords"):
                if alt in args:
                    args["query"] = args.pop(alt)
                    break
    return args

from nexus.security.policy_engine import PolicyEngine

def execute_tool(name: str, arguments: dict, policy_engine: PolicyEngine | None = None) -> ToolResult:
    """Execute a tool by name with the given arguments."""
    arguments = normalize_tool_arguments(name, arguments)
    tool_def = registry.get(name)
    if not tool_def:
        return ToolResult(
            status=ToolStatus.INVALID_INPUT,
            output=f"❌ Unknown tool: {name}",
            error=f"Unknown tool: {name}"
        )

    if policy_engine:
        decision = policy_engine.evaluate(action=name, target=str(arguments))
        if not decision.is_allowed():
            return ToolResult(
                status=ToolStatus.FAILURE,
                output=f"❌ Blocked by security policy: {decision.reason}",
                error=decision.reason
            )
    try:
        if not tool_def.handler:
            return ToolResult(
                status=ToolStatus.FAILURE,
                output=f"❌ No handler for tool: {name}"
            )
        result = tool_def.handler(**arguments)
        if isinstance(result, ToolResult):
            return result
        return ToolResult(status=ToolStatus.SUCCESS, output=str(result))
    except Exception as e:
        return ToolResult(
            status=ToolStatus.FAILURE,
            output=f"❌ Tool execution failed for {name}: {e}",
            error=str(e)
        )

