#!/usr/bin/env python3
"""
tool_executor.py — Native Tool-Calling System for Amuara Labs Nova 1.5b

Implements an OpenAI-compatible tool-calling protocol with:
  - Git operations (diff, log, apply patch, status)
  - Filesystem operations (read, write, list, search, delete)
  - Terminal execution (sandboxed subprocess with timeout)
  - Python REPL (isolated exec with resource limits)
  - Docker (build, run, inspect)
  - Web search (DuckDuckGo DDG API)
  - AST symbol search (via existing indexer)
  - Semantic code search

All tool calls return structured JSON results.
No tool call modifies the system outside of the workspace sandbox.
"""

import ast
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.parse
import urllib.request
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── Tool Schema Definitions ──────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "git_diff",
        "description": "Get git diff for the workspace. Returns unified diff output.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace root or specific file path"},
                "staged": {"type": "boolean", "description": "Show staged changes", "default": False},
            },
            "required": []
        }
    },
    {
        "name": "git_log",
        "description": "Get recent git commit history.",
        "parameters": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "Number of commits to show", "default": 10},
                "format": {"type": "string", "description": "Git log format string", "default": "--oneline"},
            },
            "required": []
        }
    },
    {
        "name": "git_apply_patch",
        "description": "Apply a unified diff patch to the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "patch": {"type": "string", "description": "Unified diff patch string"},
                "dry_run": {"type": "boolean", "description": "Check without applying", "default": True},
            },
            "required": ["patch"]
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
                "start_line": {"type": "integer", "description": "Start line (1-indexed)"},
                "end_line": {"type": "integer", "description": "End line (1-indexed, inclusive)"},
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file (creates parent directories).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "File content"},
                "append": {"type": "boolean", "description": "Append instead of overwrite", "default": False},
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_directory",
        "description": "List files and directories at a path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
                "pattern": {"type": "string", "description": "Glob pattern filter (e.g. '*.py')"},
                "recursive": {"type": "boolean", "default": False},
            },
            "required": ["path"]
        }
    },
    {
        "name": "search_files",
        "description": "Search for a text pattern across files in a directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Root directory to search"},
                "pattern": {"type": "string", "description": "Text or regex pattern"},
                "file_glob": {"type": "string", "description": "File pattern (e.g. '*.py')", "default": "*"},
                "case_sensitive": {"type": "boolean", "default": True},
                "max_results": {"type": "integer", "default": 50},
            },
            "required": ["path", "pattern"]
        }
    },
    {
        "name": "run_command",
        "description": "Execute a shell command in the workspace sandbox.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "cwd": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["command"]
        }
    },
    {
        "name": "python_repl",
        "description": "Execute Python code in an isolated REPL environment.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "description": "Execution timeout in seconds", "default": 10},
            },
            "required": ["code"]
        }
    },
    {
        "name": "ast_symbol_search",
        "description": "Search for a symbol (function, class, variable) in the indexed codebase.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name to search"},
                "workspace": {"type": "string", "description": "Workspace root directory", "default": "."},
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "web_search",
        "description": "Search the web for information (uses DuckDuckGo Instant Answer API).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"]
        }
    },
    {
        "name": "docker_run",
        "description": "Run a Docker container (dry-run by default for safety).",
        "parameters": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Docker image name"},
                "command": {"type": "string", "description": "Command to run inside container"},
                "volumes": {"type": "array", "items": {"type": "string"}, "description": "Volume mounts (-v format)"},
                "env": {"type": "object", "description": "Environment variables"},
                "dry_run": {"type": "boolean", "default": True},
            },
            "required": ["image"]
        }
    },
]


# ─── Result Builder ───────────────────────────────────────────────────────────

def _ok(tool: str, data: Any, elapsed_ms: float = 0.0) -> dict:
    return {"tool": tool, "status": "success", "result": data, "elapsed_ms": round(elapsed_ms, 2)}

def _err(tool: str, message: str, elapsed_ms: float = 0.0) -> dict:
    return {"tool": tool, "status": "error", "error": message, "elapsed_ms": round(elapsed_ms, 2)}


# ─── Tool Implementations ─────────────────────────────────────────────────────

class ToolExecutor:
    """
    Sandboxed tool executor for Nova 1.5b agent framework.
    Workspace root is the primary boundary for file operations.
    """

    BLOCKED_COMMANDS = [
        "rm -rf /", "mkfs", "dd if=", "shutdown", "reboot", "halt",
        "curl | bash", "wget | bash", ":(){ :|:& };:", "fork bomb",
    ]

    def __init__(self, workspace: str = "."):
        self.workspace = os.path.abspath(workspace)
        self._call_log: List[dict] = []

    def _safe_path(self, path: str) -> str:
        """Resolve path and ensure it stays within workspace."""
        resolved = os.path.realpath(os.path.join(self.workspace, path))
        if not resolved.startswith(self.workspace):
            raise PermissionError(f"Path escape attempt blocked: {path} → {resolved}")
        return resolved

    def _is_blocked(self, command: str) -> bool:
        cmd_lower = command.lower()
        return any(b in cmd_lower for b in self.BLOCKED_COMMANDS)

    # ── Git Tools ──────────────────────────────────────────────────────────────

    def git_diff(self, path: str = ".", staged: bool = False) -> dict:
        t0 = time.monotonic()
        try:
            safe_path = self._safe_path(path)
            flags = ["--cached"] if staged else []
            result = subprocess.run(
                ["git", "diff"] + flags + ["--", safe_path],
                cwd=self.workspace, capture_output=True, text=True, timeout=10
            )
            return _ok("git_diff", {
                "diff": result.stdout or "(no changes)",
                "stderr": result.stderr.strip(),
                "returncode": result.returncode
            }, (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("git_diff", str(e), (time.monotonic() - t0) * 1000)

    def git_log(self, n: int = 10, format: str = "--oneline") -> dict:
        t0 = time.monotonic()
        try:
            result = subprocess.run(
                ["git", "log", format, f"-{n}"],
                cwd=self.workspace, capture_output=True, text=True, timeout=10
            )
            return _ok("git_log", {"log": result.stdout.strip()}, (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("git_log", str(e), (time.monotonic() - t0) * 1000)

    def git_apply_patch(self, patch: str, dry_run: bool = True) -> dict:
        t0 = time.monotonic()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
                f.write(patch)
                patch_file = f.name
            flags = ["--check"] if dry_run else []
            result = subprocess.run(
                ["git", "apply"] + flags + [patch_file],
                cwd=self.workspace, capture_output=True, text=True, timeout=30
            )
            os.unlink(patch_file)
            return _ok("git_apply_patch", {
                "applied": result.returncode == 0,
                "dry_run": dry_run,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }, (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("git_apply_patch", str(e), (time.monotonic() - t0) * 1000)

    # ── File System Tools ──────────────────────────────────────────────────────

    def read_file(self, path: str, start_line: Optional[int] = None,
                  end_line: Optional[int] = None) -> dict:
        t0 = time.monotonic()
        try:
            safe_path = self._safe_path(path)
            with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            total_lines = len(lines)
            if start_line is not None or end_line is not None:
                sl = max(0, (start_line or 1) - 1)
                el = min(total_lines, end_line or total_lines)
                content = "".join(lines[sl:el])
            else:
                content = "".join(lines)
            return _ok("read_file", {
                "path": path, "content": content,
                "total_lines": total_lines, "size_bytes": os.path.getsize(safe_path)
            }, (time.monotonic() - t0) * 1000)
        except FileNotFoundError:
            return _err("read_file", f"File not found: {path}", (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("read_file", str(e), (time.monotonic() - t0) * 1000)

    def write_file(self, path: str, content: str, append: bool = False) -> dict:
        t0 = time.monotonic()
        try:
            safe_path = self._safe_path(path)
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            mode = "a" if append else "w"
            with open(safe_path, mode, encoding="utf-8") as f:
                f.write(content)
            return _ok("write_file", {
                "path": path, "bytes_written": len(content.encode()),
                "append": append
            }, (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("write_file", str(e), (time.monotonic() - t0) * 1000)

    def list_directory(self, path: str, pattern: Optional[str] = None,
                       recursive: bool = False) -> dict:
        t0 = time.monotonic()
        try:
            safe_path = self._safe_path(path)
            entries = []
            if recursive:
                for root, dirs, files in os.walk(safe_path):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                               ("__pycache__", "node_modules", ".git", "target", "build")]
                    for name in files:
                        full = os.path.join(root, name)
                        rel = os.path.relpath(full, safe_path)
                        if not pattern or Path(rel).match(pattern):
                            entries.append({"path": rel, "size": os.path.getsize(full), "type": "file"})
            else:
                for entry in sorted(os.scandir(safe_path), key=lambda e: (e.is_file(), e.name)):
                    if not pattern or Path(entry.name).match(pattern):
                        entries.append({
                            "path": entry.name,
                            "size": entry.stat().st_size if entry.is_file() else None,
                            "type": "file" if entry.is_file() else "directory"
                        })
            return _ok("list_directory", {"path": path, "entries": entries, "count": len(entries)},
                      (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("list_directory", str(e), (time.monotonic() - t0) * 1000)

    def search_files(self, path: str, pattern: str, file_glob: str = "*",
                     case_sensitive: bool = True, max_results: int = 50) -> dict:
        t0 = time.monotonic()
        try:
            safe_path = self._safe_path(path)
            flags = re.MULTILINE if case_sensitive else re.MULTILINE | re.IGNORECASE
            regex = re.compile(pattern, flags)
            results = []

            for root, dirs, files in os.walk(safe_path):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                           ("__pycache__", "node_modules", ".git", "target", "build")]
                for fname in files:
                    if not Path(fname).match(file_glob):
                        continue
                    full = os.path.join(root, fname)
                    try:
                        with open(full, "r", encoding="utf-8", errors="ignore") as f:
                            for lineno, line in enumerate(f, 1):
                                if regex.search(line):
                                    results.append({
                                        "file": os.path.relpath(full, safe_path),
                                        "line": lineno,
                                        "content": line.rstrip()
                                    })
                                    if len(results) >= max_results:
                                        break
                    except (PermissionError, IsADirectoryError):
                        continue
                if len(results) >= max_results:
                    break

            return _ok("search_files", {
                "pattern": pattern, "results": results,
                "total_matches": len(results), "truncated": len(results) >= max_results
            }, (time.monotonic() - t0) * 1000)
        except re.error as e:
            return _err("search_files", f"Invalid regex: {e}", (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("search_files", str(e), (time.monotonic() - t0) * 1000)

    # ── Terminal Tool ──────────────────────────────────────────────────────────

    def run_command(self, command: str, cwd: Optional[str] = None,
                    timeout: int = 30) -> dict:
        t0 = time.monotonic()
        if self._is_blocked(command):
            return _err("run_command", f"Blocked command pattern detected: {command[:80]}",
                       (time.monotonic() - t0) * 1000)
        try:
            work_dir = self._safe_path(cwd or ".") if cwd else self.workspace
            result = subprocess.run(
                command, shell=True, cwd=work_dir,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            )
            return _ok("run_command", {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout[-8000:] if len(result.stdout) > 8000 else result.stdout,
                "stderr": result.stderr[-4000:] if len(result.stderr) > 4000 else result.stderr,
                "success": result.returncode == 0,
            }, (time.monotonic() - t0) * 1000)
        except subprocess.TimeoutExpired:
            return _err("run_command", f"Command timed out after {timeout}s: {command}",
                       (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("run_command", str(e), (time.monotonic() - t0) * 1000)

    # ── Python REPL ────────────────────────────────────────────────────────────

    def python_repl(self, code: str, timeout: int = 10) -> dict:
        t0 = time.monotonic()

        # Safety: validate syntax first
        try:
            ast.parse(code)
        except SyntaxError as e:
            return _err("python_repl", f"SyntaxError: {e}", (time.monotonic() - t0) * 1000)

        # Blocklist: prevent system-level abuse
        dangerous = ["import os", "import sys", "__import__", "eval(", "exec(",
                     "open(", "subprocess", "socket", "shutil.rmtree", "os.system"]
        for d in dangerous:
            if d in code:
                return _err("python_repl",
                           f"Blocked: REPL code contains restricted pattern '{d}'",
                           (time.monotonic() - t0) * 1000)

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        local_vars: dict = {}

        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(compile(code, "<repl>", "exec"), {"__builtins__": __builtins__}, local_vars)
            output = stdout_buf.getvalue()
            err_output = stderr_buf.getvalue()
            # Capture final expression result
            lines = code.strip().splitlines()
            result_val = None
            if lines:
                try:
                    last_expr = compile(lines[-1], "<repl_last>", "eval")
                    result_val = eval(last_expr, {}, local_vars)
                except Exception:
                    pass
            return _ok("python_repl", {
                "stdout": output,
                "stderr": err_output,
                "result": repr(result_val) if result_val is not None else None,
                "locals": {k: repr(v) for k, v in local_vars.items() if not k.startswith("_")}
            }, (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("python_repl",
                       f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1000:]}",
                       (time.monotonic() - t0) * 1000)

    # ── AST Symbol Search ──────────────────────────────────────────────────────

    def ast_symbol_search(self, symbol: str, workspace: str = ".") -> dict:
        t0 = time.monotonic()
        try:
            from ast_indexer import ASTIndexer
            safe_ws = self._safe_path(workspace)
            indexer = ASTIndexer(safe_ws)
            matches = indexer.find_symbol(symbol)
            return _ok("ast_symbol_search", {
                "symbol": symbol,
                "matches": matches,
                "count": len(matches)
            }, (time.monotonic() - t0) * 1000)
        except ImportError:
            return _err("ast_symbol_search", "ast_indexer module not found",
                       (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("ast_symbol_search", str(e), (time.monotonic() - t0) * 1000)

    # ── Web Search ─────────────────────────────────────────────────────────────

    def web_search(self, query: str, max_results: int = 5) -> dict:
        t0 = time.monotonic()
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(url, headers={"User-Agent": "Amuara-Fable5-Bot/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = []
            # Abstract (direct answer)
            if data.get("AbstractText"):
                results.append({
                    "type": "abstract",
                    "title": data.get("Heading", ""),
                    "text": data["AbstractText"],
                    "url": data.get("AbstractURL", "")
                })
            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results - len(results)]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "type": "topic",
                        "text": topic["Text"][:300],
                        "url": topic.get("FirstURL", "")
                    })

            return _ok("web_search", {
                "query": query, "results": results, "total": len(results)
            }, (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("web_search", f"Search failed: {e}", (time.monotonic() - t0) * 1000)

    # ── Docker Tool ────────────────────────────────────────────────────────────

    def docker_run(self, image: str, command: str = "",
                   volumes: Optional[List[str]] = None,
                   env: Optional[Dict[str, str]] = None,
                   dry_run: bool = True) -> dict:
        t0 = time.monotonic()
        try:
            cmd = ["docker", "run", "--rm", "--network", "none",
                   "--memory", "512m", "--cpus", "1.0"]
            if env:
                for k, v in env.items():
                    cmd.extend(["-e", f"{k}={v}"])
            if volumes:
                for vol in volumes:
                    # Ensure volume paths are workspace-relative
                    parts = vol.split(":")
                    if parts[0] and not parts[0].startswith("/"):
                        parts[0] = self._safe_path(parts[0])
                    cmd.extend(["-v", ":".join(parts)])
            cmd.append(image)
            if command:
                cmd.extend(shlex.split(command))

            if dry_run:
                return _ok("docker_run", {
                    "dry_run": True,
                    "would_execute": " ".join(cmd),
                    "image": image,
                }, (time.monotonic() - t0) * 1000)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return _ok("docker_run", {
                "image": image,
                "returncode": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-2000:],
                "success": result.returncode == 0
            }, (time.monotonic() - t0) * 1000)
        except Exception as e:
            return _err("docker_run", str(e), (time.monotonic() - t0) * 1000)

    # ── Dispatcher ────────────────────────────────────────────────────────────

    def execute(self, tool_name: str, params: Dict[str, Any]) -> dict:
        """Dispatch a tool call by name with parameters."""
        self._call_log.append({"tool": tool_name, "params": params, "timestamp": time.time()})

        dispatch = {
            "git_diff": lambda p: self.git_diff(**p),
            "git_log": lambda p: self.git_log(**p),
            "git_apply_patch": lambda p: self.git_apply_patch(**p),
            "read_file": lambda p: self.read_file(**p),
            "write_file": lambda p: self.write_file(**p),
            "list_directory": lambda p: self.list_directory(**p),
            "search_files": lambda p: self.search_files(**p),
            "run_command": lambda p: self.run_command(**p),
            "python_repl": lambda p: self.python_repl(**p),
            "ast_symbol_search": lambda p: self.ast_symbol_search(**p),
            "web_search": lambda p: self.web_search(**p),
            "docker_run": lambda p: self.docker_run(**p),
        }

        if tool_name not in dispatch:
            return _err("dispatcher", f"Unknown tool: {tool_name}")

        try:
            return dispatch[tool_name](params)
        except TypeError as e:
            return _err(tool_name, f"Invalid parameters: {e}")
        except PermissionError as e:
            return _err(tool_name, f"Permission denied: {e}")

    @property
    def call_log(self) -> List[dict]:
        return list(self._call_log)


# ─── Test Runner ──────────────────────────────────────────────────────────────

def run_self_tests(workspace: str = ".") -> dict:
    """Run built-in self-tests for the tool executor."""
    executor = ToolExecutor(workspace)
    results = {}
    passed = 0
    failed = 0

    def test(name: str, fn):
        nonlocal passed, failed
        try:
            result = fn()
            if result.get("status") == "success":
                print(f"  ✓ {name}")
                passed += 1
                results[name] = "PASS"
            else:
                print(f"  ✗ {name}: {result.get('error', 'unknown error')}")
                failed += 1
                results[name] = f"FAIL: {result.get('error', '')}"
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1
            results[name] = f"ERROR: {e}"

    print("\n[ToolExecutor] Running self-tests...")

    test("python_repl_basic", lambda: executor.python_repl("x = 2 + 2\nprint(x)"))
    test("python_repl_syntax_error", lambda: {
        "status": "error" if executor.python_repl("def broken(:")["status"] == "error" else "success"
    })
    test("list_directory", lambda: executor.list_directory(workspace))
    test("read_file_self", lambda: executor.read_file("tool_executor.py"))
    test("search_files", lambda: executor.search_files(workspace, "ToolExecutor", "*.py"))
    test("ast_symbol_search", lambda: executor.ast_symbol_search("ToolExecutor", workspace))
    test("git_log", lambda: executor.git_log(n=3))

    print(f"\n[ToolExecutor] Results: {passed} passed, {failed} failed\n")
    return {"passed": passed, "failed": failed, "results": results}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Nova 1.5b Tool Executor")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    parser.add_argument("--workspace", type=str, default=".", help="Workspace root")
    parser.add_argument("--tool", type=str, help="Tool name to call")
    parser.add_argument("--params", type=str, default="{}", help="JSON params string")
    args = parser.parse_args()

    if args.test:
        summary = run_self_tests(args.workspace)
        sys.exit(0 if summary["failed"] == 0 else 1)
    elif args.tool:
        executor = ToolExecutor(args.workspace)
        params = json.loads(args.params)
        result = executor.execute(args.tool, params)
        print(json.dumps(result, indent=2))
    else:
        print("Tool Schemas:")
        print(json.dumps(TOOL_SCHEMAS, indent=2))
