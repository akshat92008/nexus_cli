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

def tool_read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> ToolResult:
    """Read file contents with line numbers."""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return ToolResult(status=ToolStatus.FAILURE, output=f"❌ File not found: {path}", error="File not found")
        if not p.is_file():
            return ToolResult(status=ToolStatus.FAILURE, output=f"❌ Not a file: {path}", error="Not a file")
        if p.stat().st_size > 2 * 1024 * 1024:
            return ToolResult(status=ToolStatus.FAILURE, output=f"❌ File too large ({_format_size(p.stat().st_size)}). Use search_code instead.", error="File too large")

        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if start_line is not None:
            try:
                start_line = int(start_line)
            except (ValueError, TypeError):
                start_line = None
        if end_line is not None:
            try:
                end_line = int(end_line)
            except (ValueError, TypeError):
                end_line = None

        start = max(1, start_line or 1)
        end = min(len(lines), end_line or len(lines))

        numbered = []
        for i in range(start - 1, end):
            numbered.append(f"{i + 1:>5} │ {lines[i].rstrip()}")

        header = f"📄 {p.name}  ({len(lines)} lines, {_format_size(p.stat().st_size)})"
        if start_line or end_line:
            header += f"  [showing lines {start}-{end}]"

        return ToolResult(status=ToolStatus.SUCCESS, output=header + "\n" + "\n".join(numbered))
    except (LookupError, OSError, TypeError, ValueError) as e:
        return ToolResult(status=ToolStatus.FAILURE, output=f"❌ Error reading file: {e}", error=str(e))

def tool_write_file(path: str, content: str) -> str:
    """Write content to a file, creating directories as needed. Tracked for undo."""
    try:
        from nexus.mutation import MutationController
        p = _resolve_path(path)

        # Snapshot before writing
        history = get_history()
        snapshot = history.snapshot_before_write(str(p))

        mutator = MutationController(p.parent if p.parent.exists() else p.parent.parent)
        res = mutator.write_file(p, content)
        if not res.success:
            return f"❌ Error writing file: {res.error}"

        # Record the change
        history.record_change(str(p), "write_file", snapshot)

        line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"✅ Wrote {line_count} lines to {p}\nDiff:\n{res.diff}" if res.diff else f"✅ Wrote {line_count} lines to {p}"
    except (OSError, TypeError, ValueError) as e:
        return f"❌ Error writing file: {e}"

def tool_edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace old_text with new_text in a file. Tracked for undo."""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return f"❌ File not found: {path}"

        with open(p, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. Exact match
        count = content.count(old_text)
        target_old = old_text

        # 2. Whitespace-insensitive fallback match if exact fails
        if count == 0:
            content_lines = content.splitlines(keepends=True)
            old_lines = old_text.splitlines()

            if old_lines:
                clean_old = [line.strip() for line in old_lines if line.strip()]
                matches = []
                for i in range(len(content_lines) - len(old_lines) + 1):
                    chunk = content_lines[i : i + len(old_lines)]
                    clean_chunk = [line.strip() for line in chunk if line.strip()]
                    if clean_chunk == clean_old:
                        matches.append((i, "".join(chunk)))

                if len(matches) == 1:
                    target_old = matches[0][1]
                    count = 1

        if count == 0:
            # Diagnostic feedback for LLM — fail clearly, never silently replace the whole file
            first_line = old_text.splitlines()[0] if old_text.strip() else old_text
            content_lines = content.splitlines()
            similar = [
                f"L{index + 1}: {line.strip()[:80]}"
                for index, line in enumerate(content_lines)
                if first_line.strip() in line.strip() or line.strip() in first_line.strip()
            ]
            hint = f"\nSimilar lines in {p.name}:\n" + "\n".join(similar[:5]) if similar else ""
            return f"❌ Text not found in {p.name}. Make sure old_text matches exactly.{hint}"

        if count > 1:
            return f"⚠️ Found {count} occurrences of old_text in {p.name}. Provide more surrounding lines to make old_text unique."

        # Snapshot before editing
        history = get_history()
        snapshot = history.snapshot_before_write(str(p))

        new_content = content.replace(target_old, new_text, 1)
        from nexus.mutation import MutationController
        mutator = MutationController(p.parent)
        res = mutator.write_file(p, new_content)
        if not res.success:
            return f"❌ Error editing file: {res.error}"

        history.record_change(str(p), "edit_file", snapshot)

        old_lc = old_text.count("\n") + 1
        new_lc = new_text.count("\n") + 1
        return f"✅ Edited {p.name}: replaced {old_lc} lines → {new_lc} lines\nDiff:\n{res.diff}"
    except (LookupError, OSError, TypeError, ValueError) as e:
        return f"❌ Error editing file: {e}"

def tool_patch_file(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """Apply a line-range based edit. Tracked for undo."""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return f"❌ File not found: {path}"

        with open(p, "r", encoding="utf-8") as f:
            lines = f.readlines()

        try:
            start_line = int(start_line)
            end_line = int(end_line)
        except (ValueError, TypeError):
            return "❌ start_line and end_line must be integers"

        if start_line < 1 or start_line > len(lines) + 1:
            return f"❌ start_line {start_line} out of range (file has {len(lines)} lines)"

        if end_line != 0 and end_line < start_line:
            return f"❌ end_line ({end_line}) must be >= start_line ({start_line}) or 0 for insert mode"

        # Snapshot
        history = get_history()
        snapshot = history.snapshot_before_write(str(p))

        new_lines = new_content.split("\n") if new_content else []
        # Ensure each new line ends with \n except possibly the last
        new_lines = [line + "\n" for line in new_lines]

        if end_line == 0:
            # Insert before start_line
            for i, line in enumerate(new_lines):
                lines.insert(start_line - 1 + i, line)
        else:
            # Replace lines[start_line-1 : end_line] with new_lines
            end_line = min(end_line, len(lines))
            lines[start_line - 1 : end_line] = new_lines

        new_content_final = "".join(lines)

        from nexus.mutation import MutationController
        mutator = MutationController(p.parent)
        res = mutator.write_file(p, new_content_final)
        if not res.success:
            return f"❌ Error patching file: {res.error}"

        history.record_change(str(p), "patch_file", snapshot)
        return f"✅ Patched {p.name}: lines {start_line}-{end_line} → {len(new_lines)} new lines\nDiff:\n{res.diff}"
    except (LookupError, OSError, TypeError, ValueError) as e:
        return f"❌ Error patching file: {e}"

def tool_file_info(path: str) -> str:
    """Get file/directory metadata."""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return f"❌ Path not found: {path}"

        stat = p.stat()
        info = [f"📋 {p.name}"]
        info.append(f"  Type:      {'directory' if p.is_dir() else 'file'}")
        info.append(f"  Path:      {p}")
        info.append(f"  Size:      {_format_size(stat.st_size)}")
        info.append(
            f"  Modified:  {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}"
        )
        info.append(f"  Perms:     {oct(stat.st_mode)[-3:]}")

        if p.is_file():
            mime = mimetypes.guess_type(str(p))[0] or "unknown"
            info.append(f"  MIME:      {mime}")
            # Count lines for text files
            if stat.st_size < 5 * 1024 * 1024:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        line_count = sum(1 for _ in f)
                    info.append(f"  Lines:     {line_count}")
                except (UnicodeDecodeError, OSError):
                    info.append("  Lines:     (binary file)")
            # MD5 for small files
            if stat.st_size < 1024 * 1024:
                h = hashlib.md5(p.read_bytes()).hexdigest()
                info.append(f"  MD5:       {h}")

        return "\n".join(info)
    except (OSError, TypeError, ValueError) as e:
        return f"❌ Error getting file info: {e}"

def tool_diff_files(file_a: str, file_b: str) -> str:
    """Show unified diff between two files."""
    try:
        import difflib

        pa = _resolve_path(file_a)
        pb = _resolve_path(file_b)

        if not pa.exists():
            return f"❌ File not found: {file_a}"
        if not pb.exists():
            return f"❌ File not found: {file_b}"

        with open(pa, "r", encoding="utf-8", errors="replace") as f:
            lines_a = f.readlines()
        with open(pb, "r", encoding="utf-8", errors="replace") as f:
            lines_b = f.readlines()

        diff = difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=str(pa.name),
            tofile=str(pb.name),
        )
        result = "".join(diff)
        if not result:
            return f"✅ Files are identical: {pa.name} == {pb.name}"
        return f"📝 Diff: {pa.name} vs {pb.name}\n{result}"
    except (ImportError, OSError, TypeError, ValueError) as e:
        return f"❌ Error diffing files: {e}"

def tool_list_directory(
    path: str | None = None, recursive: bool = False, max_depth: int = 3
) -> str:
    """List directory contents."""
    try:
        dir_path = _resolve_path(path or _tool_working_dir.get() or os.getcwd())
        if not dir_path.is_dir():
            return f"❌ Not a directory: {dir_path}"

        items = []

        def _list(p: Path, depth: int, prefix: str = ""):
            if depth > max_depth:
                return
            try:
                entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError:
                return

            for entry in entries:
                if _should_ignore(entry):
                    continue
                if entry.is_dir():
                    items.append(f"{prefix}📁 {entry.name}/")
                    if recursive:
                        _list(entry, depth + 1, prefix + "   ")
                else:
                    size = _format_size(entry.stat().st_size)
                    items.append(f"{prefix}📄 {entry.name}  ({size})")

        _list(dir_path, 0)

        if not items:
            return f"📁 {dir_path} (empty)"
        return f"📁 {dir_path}\n" + "\n".join(items)
    except (OSError, TypeError, ValueError) as e:
        return f"❌ Error listing directory: {e}"

def tool_find_files(pattern: str, directory: str | None = None) -> str:
    """Find files matching a glob pattern."""
    try:
        search_dir = _resolve_path(directory or _tool_working_dir.get() or os.getcwd())
        matches = []
        for p in search_dir.rglob(pattern):
            if any(part in IGNORE_DIRS for part in p.parts):
                continue
            if _should_ignore(p):
                continue
            rel = p.relative_to(search_dir)
            if p.is_file():
                matches.append(f"  📄 {rel}  ({_format_size(p.stat().st_size)})")
            else:
                matches.append(f"  📁 {rel}/")
            if len(matches) >= 100:
                break

        if not matches:
            return f"🔍 No files matching '{pattern}' in {search_dir}"
        return f"🔍 Found {len(matches)} matches for '{pattern}':\n" + "\n".join(matches)
    except (LookupError, OSError, RuntimeError, TypeError, ValueError) as e:
        return f"❌ Error finding files: {e}"

class _PolicyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Revalidate every redirect before urllib follows it."""

    def __init__(self, policy, original_url: str):
        super().__init__()
        self.policy = policy
        self.original_url = original_url

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urllib.parse.urljoin(req.full_url, newurl)
        violation = self.policy.check_redirect(self.original_url, destination)
        if violation:
            raise urllib.error.URLError(violation.reason)
        return super().redirect_request(req, fp, code, msg, headers, destination)

