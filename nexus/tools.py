"""
Coding tools — the agent's hands. 20 tools for file I/O, shell, git, web, and more.

Tools:
  File:    read_file, write_file, edit_file, patch_file, multi_edit, file_info, diff_files
  Search:  search_code, list_directory, find_files, get_project_structure
  Shell:   run_command, process_run
  Git:     git_status, git_diff, git_commit, git_log, git_branch
  Web:     web_fetch, web_search
"""

import os
import re
import json
import subprocess
import fnmatch
import hashlib
import mimetypes
import urllib.request
import urllib.error
import html
from pathlib import Path
from datetime import datetime

from nexus.history import get_history


# ── Tool definitions (OpenAI function-calling format) ────────────────────────

TOOL_DEFINITIONS = [
    # ─── FILE TOOLS ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the given path. Returns the file text with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative file path to read.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional 1-based start line (inclusive).",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional 1-based end line (inclusive).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content. Parent directories are created automatically. Tracked for undo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to write to.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace a specific string in a file with new content. Use for surgical edits. The old_text must match exactly and be unique. Tracked for undo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to edit.",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "The exact text to find and replace (must be unique in the file).",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "The replacement text.",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_file",
            "description": "Apply a line-range based edit to a file. Can insert, replace, or delete lines by line number. Tracked for undo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to patch.",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "1-based start line number for the edit range.",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "1-based end line number (inclusive). Use same as start_line to replace one line. Use 0 for end_line to insert before start_line.",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "The new content to insert/replace. Use empty string to delete lines.",
                    },
                },
                "required": ["path", "start_line", "end_line", "new_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "multi_edit",
            "description": "Apply multiple edits across one or more files in a single call. Each edit specifies a file, old_text, and new_text. All edits are atomic per-file. Tracked for undo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "edits": {
                        "type": "array",
                        "description": "Array of edit objects.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "File path"},
                                "old_text": {"type": "string", "description": "Text to find"},
                                "new_text": {"type": "string", "description": "Replacement text"},
                            },
                            "required": ["path", "old_text", "new_text"],
                        },
                    },
                },
                "required": ["edits"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_info",
            "description": "Get detailed metadata about a file: size, permissions, last modified, type, encoding, line count.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File or directory path.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "diff_files",
            "description": "Show a unified diff between two files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_a": {"type": "string", "description": "Path to the first file."},
                    "file_b": {"type": "string", "description": "Path to the second file."},
                },
                "required": ["file_a", "file_b"],
            },
        },
    },
    # ─── SEARCH TOOLS ────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for a pattern across files in a directory (like grep -rn). Returns matching lines with file paths and line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (regex supported).",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory to search in (default: current directory).",
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter files, e.g. '*.py' or '*.js'.",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List contents of a directory with file sizes and types.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list (default: current directory).",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "If true, list recursively (default: false).",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Max depth for recursive listing (default: 3).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": "Find files matching a glob pattern in a directory tree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. '**/*.py' or 'config.*'.",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Root directory to search (default: current directory).",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_structure",
            "description": "Get a tree view of the project directory structure, respecting .gitignore patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Root path (default: current directory).",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth to traverse (default: 4).",
                    },
                },
                "required": [],
            },
        },
    },
    # ─── SHELL TOOLS ─────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command and return stdout/stderr. Use for running code, tests, git, package managers, etc. Blocks until completion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory for the command.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 120).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "process_run",
            "description": "Start a background process (non-blocking). Returns the PID. Useful for starting servers or long-running tasks. Output is captured and can be retrieved later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run in the background.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    # ─── GIT TOOLS ───────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show the current git status: branch name, staged files, modified files, untracked files. Provides a comprehensive overview of the repository state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cwd": {
                        "type": "string",
                        "description": "Repository path (default: current directory).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show git diffs. By default shows unstaged changes. Use staged=true for staged changes, or provide a commit hash/range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Optional: commit hash, branch name, or range like 'HEAD~3..HEAD'. Omit for working directory changes.",
                    },
                    "staged": {
                        "type": "boolean",
                        "description": "If true, show staged (cached) changes instead of unstaged.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional: limit diff to a specific file.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Repository path (default: current directory).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Stage files and create a git commit. Can stage all changes, specific files, or just commit what's already staged.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Commit message.",
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: specific files to stage before committing. Omit to commit what's already staged.",
                    },
                    "all": {
                        "type": "boolean",
                        "description": "If true, stage ALL changes (git add -A) before committing.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Repository path (default: current directory).",
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "View recent git commit history with hash, author, date, and message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of commits to show (default: 15).",
                    },
                    "oneline": {
                        "type": "boolean",
                        "description": "If true, show compact one-line format (default: true).",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional: show commits that touched a specific file.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Repository path (default: current directory).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_branch",
            "description": "List, create, switch, or delete git branches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "create", "switch", "delete"],
                        "description": "Action to perform (default: list).",
                    },
                    "name": {
                        "type": "string",
                        "description": "Branch name (required for create/switch/delete).",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Repository path (default: current directory).",
                    },
                },
                "required": [],
            },
        },
    },
    # ─── WEB TOOLS ───────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a URL and extract readable text content. Use for reading documentation, APIs, or web pages. Strips HTML and returns clean text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch.",
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum characters to return (default: 10000).",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information. Returns relevant results with titles, URLs, and snippets. Uses DuckDuckGo (no API key needed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 5).",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ── Ignore patterns ─────────────────────────────────────────────────────────

IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".next", ".venv", "venv",
    "dist", "build", ".cache", ".tox", ".mypy_cache", ".pytest_cache",
    "env", ".env", ".idea", ".vscode", "target", "coverage",
    ".nexusai", ".ruff_cache",
}

IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".o", ".a", ".class", ".jar",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".7z",
    ".pdf", ".doc", ".docx",
}


def _should_ignore(path: Path) -> bool:
    """Check if a path should be ignored."""
    if path.name.startswith(".") and path.name not in (".env", ".gitignore", ".eslintrc", ".prettierrc", ".nexusai"):
        return True
    if path.is_dir() and path.name in IGNORE_DIRS:
        return True
    if path.is_file() and path.suffix.lower() in IGNORE_EXTENSIONS:
        return True
    return False


def _format_size(size: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}" if unit != "B" else f"{size}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _run_git(args: list[str], cwd: str | None = None) -> tuple[bool, str]:
    """Run a git command and return (success, output)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd or os.getcwd(),
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
    except Exception as e:
        return False, f"❌ Git error: {e}"


def _strip_html(html_text: str) -> str:
    """Very simple HTML-to-text converter."""
    # Remove script and style elements
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    # Trim lines
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(line for line in lines if line)
    return text.strip()


def _resolve_path(path_str: str) -> Path:
    """
    Intelligently resolve file and directory paths.
    Expands ~, handles relative paths, and maps 'desktop/...' or 'Desktop/...'
    to the user's actual Desktop directory if applicable.
    """
    if not path_str:
        return Path.cwd()

    path_str = str(path_str).strip()
    clean_path = path_str.replace("\\", "/")

    # Handle explicit desktop paths like 'desktop/calculator' or 'Desktop/app.py'
    if clean_path.lower().startswith("desktop/") or clean_path.lower() == "desktop":
        desktop_dir = Path.home() / "Desktop"
        if desktop_dir.exists():
            if clean_path.lower() == "desktop":
                return desktop_dir.resolve()
            relative_part = clean_path.split("/", 1)[1]
            return (desktop_dir / relative_part).resolve()

    return Path(path_str).expanduser().resolve()


# ── Tool implementations ────────────────────────────────────────────────────

def tool_read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read file contents with line numbers."""
    try:
        p = _resolve_path(path)
        if not p.exists():
            return f"❌ File not found: {path}"
        if not p.is_file():
            return f"❌ Not a file: {path}"
        if p.stat().st_size > 2 * 1024 * 1024:
            return f"❌ File too large ({_format_size(p.stat().st_size)}). Use search_code instead."

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

        return header + "\n" + "\n".join(numbered)
    except Exception as e:
        return f"❌ Error reading file: {e}"


def tool_write_file(path: str, content: str) -> str:
    """Write content to a file, creating directories as needed. Tracked for undo."""
    try:
        p = _resolve_path(path)

        # Snapshot before writing
        history = get_history()
        snapshot = history.snapshot_before_write(str(p))

        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)

        # Record the change
        history.record_change(str(p), "write_file", snapshot)

        line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"✅ Wrote {line_count} lines to {p}"
    except Exception as e:
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
            # Diagnostic feedback for LLM
            first_line = old_text.splitlines()[0] if old_text.strip() else old_text
            content_lines = content.splitlines()
            similar = [f"L{i+1}: {l.strip()[:80]}" for i, l in enumerate(content_lines) if first_line.strip() in l.strip() or l.strip() in first_line.strip()]
            hint = f"\nSimilar lines in {p.name}:\n" + "\n".join(similar[:5]) if similar else ""
            return f"❌ Text not found in {p.name}. Make sure old_text matches exactly.{hint}"

        if count > 1:
            return f"⚠️ Found {count} occurrences of old_text in {p.name}. Provide more surrounding lines to make old_text unique."

        # Snapshot before editing
        history = get_history()
        snapshot = history.snapshot_before_write(str(p))

        new_content = content.replace(target_old, new_text, 1)
        with open(p, "w", encoding="utf-8") as f:
            f.write(new_content)

        history.record_change(str(p), "edit_file", snapshot)

        old_lc = old_text.count("\n") + 1
        new_lc = new_text.count("\n") + 1
        return f"✅ Edited {p.name}: replaced {old_lc} lines → {new_lc} lines"
    except Exception as e:
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
            return f"❌ start_line and end_line must be integers"

        if start_line < 1 or start_line > len(lines) + 1:
            return f"❌ start_line {start_line} out of range (file has {len(lines)} lines)"

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

        with open(p, "w", encoding="utf-8") as f:
            f.writelines(lines)

        history.record_change(str(p), "patch_file", snapshot)
        return f"✅ Patched {p.name}: lines {start_line}-{end_line} → {len(new_lines)} new lines"
    except Exception as e:
        return f"❌ Error patching file: {e}"


def tool_multi_edit(edits: list[dict]) -> str:
    """Apply multiple edits across files. Tracked for undo."""
    results = []
    for i, edit in enumerate(edits):
        path = edit.get("path", "")
        old_text = edit.get("old_text", "")
        new_text = edit.get("new_text", "")
        if not path:
            results.append(f"  {i+1}. ❌ Missing path")
            continue
        result = tool_edit_file(path, old_text, new_text)
        results.append(f"  {i+1}. {result}")

    success_count = sum(1 for r in results if "✅" in r)
    header = f"📝 Multi-edit: {success_count}/{len(edits)} succeeded"
    return header + "\n" + "\n".join(results)


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
        info.append(f"  Modified:  {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
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
    except Exception as e:
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
            lines_a, lines_b,
            fromfile=str(pa.name),
            tofile=str(pb.name),
        )
        result = "".join(diff)
        if not result:
            return f"✅ Files are identical: {pa.name} == {pb.name}"
        return f"📝 Diff: {pa.name} vs {pb.name}\n{result}"
    except Exception as e:
        return f"❌ Error diffing files: {e}"


def tool_run_command(command: str, cwd: str | None = None, timeout: float | int | str = 120) -> str:
    """Execute a shell command."""
    try:
        work_dir = cwd or os.getcwd()
        if timeout is not None:
            try:
                timeout = float(timeout)
            except (ValueError, TypeError):
                timeout = 120.0

        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "CI": "true",
            "DEBIAN_FRONTEND": "noninteractive",
            "PAGER": "cat",
            "PYTHONUNBUFFERED": "1",
            "TERM": "dumb",
        }

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=work_dir,
            timeout=timeout,
            env=env,
        )

        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"[stderr]\n{result.stderr}")

        output = "\n".join(output_parts) or "(no output)"

        # Truncate very long output
        if len(output) > 20000:
            output = output[:9000] + f"\n\n... ({len(output) - 18000} chars truncated) ...\n\n" + output[-9000:]

        status = "✅" if result.returncode == 0 else f"❌ (exit code {result.returncode})"
        return f"{status} $ {command}\n{output}"
    except subprocess.TimeoutExpired:
        return f"⏰ Command timed out after {timeout}s: {command}"
    except Exception as e:
        return f"❌ Error running command: {e}"


# Background processes tracking
_bg_processes: dict[int, dict] = {}

def tool_process_run(command: str, cwd: str | None = None) -> str:
    """Start a background process."""
    try:
        work_dir = cwd or os.getcwd()
        log_dir = Path.home() / ".nexusai" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stdout_log = log_dir / f"bg_{ts}_stdout.log"
        stderr_log = log_dir / f"bg_{ts}_stderr.log"

        stdout_f = open(stdout_log, "w")
        stderr_f = open(stderr_log, "w")

        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=stdout_f,
                stderr=stderr_f,
                cwd=work_dir,
                env={**os.environ},
            )
        finally:
            # Close file handles in the parent — the child process
            # has its own copies of the file descriptors
            stdout_f.close()
            stderr_f.close()

        _bg_processes[proc.pid] = {
            "command": command,
            "pid": proc.pid,
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
            "started": datetime.now().isoformat(),
            "process": proc,
        }

        return (
            f"✅ Background process started\n"
            f"  PID:    {proc.pid}\n"
            f"  CMD:    {command}\n"
            f"  Stdout: {stdout_log}\n"
            f"  Stderr: {stderr_log}"
        )
    except Exception as e:
        return f"❌ Error starting background process: {e}"


def tool_search_code(pattern: str, directory: str | None = None, file_pattern: str | None = None) -> str:
    """Search for a pattern across files."""
    try:
        search_dir = _resolve_path(directory or os.getcwd())
        if not search_dir.is_dir():
            return f"❌ Not a directory: {search_dir}"

        matches = []
        max_matches = 50
        regex = re.compile(pattern, re.IGNORECASE)

        for root, dirs, files in os.walk(search_dir):
            # Filter ignored dirs
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

            for fname in files:
                if file_pattern and not fnmatch.fnmatch(fname, file_pattern):
                    continue
                fpath = Path(root) / fname
                if _should_ignore(fpath):
                    continue

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line):
                                rel = fpath.relative_to(search_dir)
                                matches.append(f"  {rel}:{i}  │ {line.rstrip()}")
                                if len(matches) >= max_matches:
                                    break
                except (OSError, UnicodeDecodeError):
                    continue

                if len(matches) >= max_matches:
                    break
            if len(matches) >= max_matches:
                break

        if not matches:
            return f"🔍 No matches for /{pattern}/ in {search_dir}"

        header = f"🔍 Found {len(matches)} matches for /{pattern}/:"
        if len(matches) == max_matches:
            header += f" (capped at {max_matches})"
        return header + "\n" + "\n".join(matches)
    except Exception as e:
        return f"❌ Error searching: {e}"


def tool_list_directory(path: str | None = None, recursive: bool = False, max_depth: int = 3) -> str:
    """List directory contents."""
    try:
        dir_path = _resolve_path(path or os.getcwd())
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
    except Exception as e:
        return f"❌ Error listing directory: {e}"


def tool_find_files(pattern: str, directory: str | None = None) -> str:
    """Find files matching a glob pattern."""
    try:
        search_dir = _resolve_path(directory or os.getcwd())
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
    except Exception as e:
        return f"❌ Error finding files: {e}"


def tool_get_project_structure(path: str | None = None, max_depth: int = 4) -> str:
    """Generate a tree view of the project."""
    try:
        root = _resolve_path(path or os.getcwd())
        lines = [f"🌳 {root.name}/"]

        def _tree(p: Path, prefix: str, depth: int):
            if depth >= max_depth:
                return
            try:
                entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except PermissionError:
                return

            # Filter
            entries = [e for e in entries if not _should_ignore(e)]
            for i, entry in enumerate(entries):
                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                if entry.is_dir():
                    lines.append(f"{prefix}{connector}{entry.name}/")
                    ext = "    " if is_last else "│   "
                    _tree(entry, prefix + ext, depth + 1)
                else:
                    lines.append(f"{prefix}{connector}{entry.name}")

        _tree(root, "", 0)
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error getting structure: {e}"


# ─── GIT TOOL IMPLEMENTATIONS ───────────────────────────────────────────

def tool_git_status(cwd: str | None = None) -> str:
    """Show comprehensive git status."""
    work_dir = str(_resolve_path(cwd or os.getcwd()))

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
    work_dir = str(_resolve_path(cwd or os.getcwd()))
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
        full_diff = full_diff[:7000] + f"\n\n... ({len(full_diff) - 14000} chars truncated) ...\n\n" + full_diff[-7000:]

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
    work_dir = str(_resolve_path(cwd or os.getcwd()))
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
    work_dir = str(_resolve_path(cwd or os.getcwd()))
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
    work_dir = str(_resolve_path(cwd or os.getcwd()))
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


# ─── WEB TOOL IMPLEMENTATIONS ───────────────────────────────────────────

def tool_web_fetch(url: str, max_length: int = 10000) -> str:
    """Fetch a URL and extract readable text."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "NexusAI/1.0 (coding-agent)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(500_000)  # Max 500KB

        # Decode
        encoding = "utf-8"
        if "charset=" in content_type:
            encoding = content_type.split("charset=")[-1].split(";")[0].strip()
        text = raw.decode(encoding, errors="replace")

        # Strip HTML if needed
        if "html" in content_type.lower():
            text = _strip_html(text)

        # Truncate
        if len(text) > max_length:
            text = text[:max_length] + f"\n\n... (truncated, {len(text)} total chars)"

        return f"🌐 Fetched {url}\n\n{text}"
    except urllib.error.HTTPError as e:
        return f"❌ HTTP {e.code}: {e.reason} — {url}"
    except urllib.error.URLError as e:
        return f"❌ URL error: {e.reason} — {url}"
    except Exception as e:
        return f"❌ Error fetching URL: {e}"


def tool_web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo HTML (no API key needed)."""
    try:
        # Use DuckDuckGo HTML search
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "NexusAI/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html_text = resp.read(200_000).decode("utf-8", errors="replace")

        # Parse results (simple regex extraction)
        results = []
        # DuckDuckGo HTML has results in <a class="result__a"> tags
        result_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL,
        )

        for match in result_pattern.finditer(html_text):
            if len(results) >= max_results:
                break
            link = match.group(1)
            title = _strip_html(match.group(2)).strip()
            snippet = _strip_html(match.group(3)).strip()

            # DuckDuckGo wraps links in a redirect, extract the actual URL
            if "uddg=" in link:
                actual_url = urllib.parse.unquote(link.split("uddg=")[-1].split("&")[0])
            else:
                actual_url = link

            if title and actual_url:
                results.append(f"  {len(results)+1}. {title}\n     {actual_url}\n     {snippet}\n")

        if not results:
            return f"🔍 No results found for: {query}"

        return f"🔍 Search results for '{query}':\n\n" + "\n".join(results)
    except Exception as e:
        return f"❌ Search error: {e}"


# ── Dispatch ─────────────────────────────────────────────────────────────────

TOOL_DISPATCH = {
    # File tools
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "patch_file": tool_patch_file,
    "multi_edit": tool_multi_edit,
    "file_info": tool_file_info,
    "diff_files": tool_diff_files,
    # Search tools
    "search_code": tool_search_code,
    "list_directory": tool_list_directory,
    "find_files": tool_find_files,
    "get_project_structure": tool_get_project_structure,
    # Shell tools
    "run_command": tool_run_command,
    "process_run": tool_process_run,
    # Git tools
    "git_status": tool_git_status,
    "git_diff": tool_git_diff,
    "git_commit": tool_git_commit,
    "git_log": tool_git_log,
    "git_branch": tool_git_branch,
    # Web tools
    "web_fetch": tool_web_fetch,
    "web_search": tool_web_search,
}


def normalize_tool_arguments(name: str, args: dict) -> dict:
    """Normalize common tool parameter name variations from LLMs."""
    args = dict(args)
    if name in ("read_file", "write_file", "edit_file", "patch_file", "file_info"):
        if "path" not in args:
            for alt in ("file_path", "file", "filename", "filepath", "target_file"):
                if alt in args:
                    args["path"] = args.pop(alt)
                    break
    elif name in ("run_command", "process_run"):
        if "command" not in args:
            for alt in ("cmd", "shell_command", "script", "exec"):
                if alt in args:
                    args["command"] = args.pop(alt)
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


def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments."""
    arguments = normalize_tool_arguments(name, arguments)
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        return f"❌ Unknown tool: {name}"
    try:
        return fn(**arguments)
    except TypeError as e:
        return f"❌ Invalid arguments for {name}: {e}"

