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

def _run_git(args: list[str], cwd: str | None = None) -> tuple[bool, str]:
    """Run a git command and return (success, output)."""
    try:
        # SECURITY CLASSIFICATION: INTERNAL_GIT_OP
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd or _tool_working_dir.get() or os.getcwd(),
            timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        return result.returncode == 0, output.strip()
    except FileNotFoundError:
        return False, "❌ git is not installed or not in PATH"
    except subprocess.TimeoutExpired:
        return False, "⏰ Git command timed out"
    except (LookupError, OSError, RuntimeError, TypeError, ValueError) as e:
        return False, f"❌ Git error: {e}"

def tool_git_status(cwd: str | None = None) -> str:
    """Show comprehensive git status."""
    work_dir = str(_resolve_path(cwd or _tool_working_dir.get() or os.getcwd()))

    # Get branch
    ok, branch = _run_git(["branch", "--show-current"], work_dir)
    if not ok:
        return f"❌ Not a git repository or git error: {branch}"

    # Get status
    _, status = _run_git(["status", "--porcelain", "-b"], work_dir)

    # Get commit count
    _, log_count = _run_git(["rev-list", "--count", "HEAD"], work_dir)

    # Get remote
    _, remote = _run_git(["remote", "-v"], work_dir)

    # Parse status
    staged, modified, untracked, deleted = [], [], [], []
    for line in status.split("\n"):
        if not line or line.startswith("##"):
            continue
        x, y = line[0], line[1]
        fname = line[3:].strip()
        if x in "MADRC":
            staged.append(f"    {x} {fname}")
        if y == "M":
            modified.append(f"    M {fname}")
        elif y == "D":
            deleted.append(f"    D {fname}")
        elif y == "?":
            untracked.append(f"    ? {fname}")

    parts = [f"🌿 Branch: {branch or '(detached HEAD)'}"]
    if log_count.strip().isdigit():
        parts.append(f"📊 Commits: {log_count.strip()}")
    if remote:
        remote_line = remote.split("\n")[0] if remote else ""
        parts.append(f"🔗 Remote: {remote_line}")

    if staged:
        parts.append(f"\n✅ Staged ({len(staged)}):")
        parts.extend(staged)
    if modified:
        parts.append(f"\n📝 Modified ({len(modified)}):")
        parts.extend(modified)
    if deleted:
        parts.append(f"\n🗑️  Deleted ({len(deleted)}):")
        parts.extend(deleted)
    if untracked:
        parts.append(f"\n❓ Untracked ({len(untracked)}):")
        parts.extend(untracked)
    if not staged and not modified and not untracked and not deleted:
        parts.append("\n✨ Working tree clean")

    return "\n".join(parts)

def tool_git_diff(
    target: str | None = None,
    staged: bool = False,
    file_path: str | None = None,
    cwd: str | None = None,
) -> str:
    """Show git diffs."""
    work_dir = str(_resolve_path(cwd or _tool_working_dir.get() or os.getcwd()))
    args = ["diff"]
    if staged:
        args.append("--cached")
    if target:
        args.append(target)
    if file_path:
        args.extend(["--", file_path])

    args.extend(["--stat"])
    ok, stat_output = _run_git(args, work_dir)

    # Also get the full diff
    full_args = ["diff"]
    if staged:
        full_args.append("--cached")
    if target:
        full_args.append(target)
    if file_path:
        full_args.extend(["--", file_path])

    _, full_diff = _run_git(full_args, work_dir)

    if not full_diff and not stat_output:
        ctx = "staged" if staged else "unstaged"
        return f"✨ No {ctx} changes{f' in {file_path}' if file_path else ''}"

    # Truncate if massive
    if len(full_diff) > 15000:
        full_diff = (
            full_diff[:7000]
            + f"\n\n... ({len(full_diff) - 14000} chars truncated) ...\n\n"
            + full_diff[-7000:]
        )

    parts = []
    if stat_output:
        parts.append(f"📊 Summary:\n{stat_output}")
    parts.append(f"\n{full_diff}")
    return "\n".join(parts)

def tool_git_commit(
    message: str,
    files: list[str] | None = None,
    all: bool = False,
    cwd: str | None = None,
) -> str:
    """Stage and commit."""
    work_dir = str(_resolve_path(cwd or _tool_working_dir.get() or os.getcwd()))
    # Stage files
    if all:
        ok, out = _run_git(["add", "-A"], work_dir)
        if not ok:
            return f"❌ Failed to stage files: {out}"
    elif files:
        ok, out = _run_git(["add"] + files, work_dir)
        if not ok:
            return f"❌ Failed to stage files: {out}"

    # Commit
    ok, out = _run_git(["commit", "-m", message], work_dir)
    if not ok:
        if "nothing to commit" in out:
            return "ℹ️  Nothing to commit. Stage changes first with git_commit(all=true) or specify files."
        return f"❌ Commit failed: {out}"

    # Get the short hash
    _, hash_out = _run_git(["rev-parse", "--short", "HEAD"], work_dir)

    return f"✅ Committed: [{hash_out.strip()}] {message}\n{out}"

def tool_git_log(
    count: int = 15,
    oneline: bool = True,
    file_path: str | None = None,
    cwd: str | None = None,
) -> str:
    """View commit history."""
    work_dir = str(_resolve_path(cwd or _tool_working_dir.get() or os.getcwd()))
    args = ["log", f"-{count}"]
    if oneline:
        args.append("--oneline")
    else:
        args.extend(["--format=%h %an %ad %s", "--date=short"])
    if file_path:
        args.extend(["--", file_path])

    ok, output = _run_git(args, work_dir)
    if not ok:
        return f"❌ Git log failed: {output}"

    return f"📜 Recent commits:\n{output}" if output else "📜 No commits yet"

def tool_git_branch(
    action: str = "list",
    name: str | None = None,
    cwd: str | None = None,
) -> str:
    """Manage branches."""
    work_dir = str(_resolve_path(cwd or _tool_working_dir.get() or os.getcwd()))
    if action == "list":
        ok, output = _run_git(["branch", "-a"], work_dir)
        return f"🌿 Branches:\n{output}" if ok else f"❌ {output}"

    if not name:
        return f"❌ Branch name required for '{action}'"

    if action == "create":
        ok, output = _run_git(["checkout", "-b", name], work_dir)
        return f"✅ Created and switched to branch: {name}" if ok else f"❌ {output}"

    elif action == "switch":
        ok, output = _run_git(["checkout", name], work_dir)
        return f"✅ Switched to branch: {name}" if ok else f"❌ {output}"

    elif action == "delete":
        ok, output = _run_git(["branch", "-d", name], work_dir)
        return f"✅ Deleted branch: {name}" if ok else f"❌ {output}"

    return f"❌ Unknown action: {action}. Use list/create/switch/delete."

def tool_github_list_issues(limit: int = 10) -> str:
    try:
        from nexus.github import GitHubIntegration

        issues = GitHubIntegration.list_issues(limit=limit)
        if not issues:
            return "No open issues found."
        lines = []
        for i in issues:
            lines.append(f"#{i.get('number')} [{i.get('state')}] {i.get('title')}")
        return "\n".join(lines)
    except (ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError) as e:
        return f"❌ GitHub Error: {e}"

def tool_github_view_issue(number: str) -> str:
    try:
        from nexus.github import GitHubIntegration

        issue = GitHubIntegration.view_issue(number)
        if not issue:
            return f"❌ Issue #{number} not found."
        comments = "\n".join(
            f"- {item.get('author', {}).get('login', 'unknown')}: {item.get('body', '')}"
            for item in issue.get("comments", [])
        )
        return (
            f"Issue #{issue.get('number')}: {issue.get('title')}\n"
            f"State: {issue.get('state')}\n"
            f"URL: {issue.get('url')}\n\n"
            f"{issue.get('body', '(no body)')}\n\n"
            f"Comments:\n{comments or '(none)'}"
        )
    except (ImportError, LookupError, OSError, RuntimeError, TypeError, ValueError) as e:
        return f"❌ GitHub Error: {e}"

def tool_github_create_pr(title: str, body: str, base: str = "") -> str:
    try:
        from nexus.github import GitHubIntegration

        url = GitHubIntegration.create_pull_request(title, body, base)
        return f"✅ Pull request created successfully: {url}"
    except ImportError as e:
        return f"❌ GitHub Error: {e}"

