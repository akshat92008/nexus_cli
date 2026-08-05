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

def tool_run_command(
    command: str,
    cwd: str | None = None,
    timeout: float | int | str = 120,
    network: bool = False,
    require_os_isolation: bool = False,
) -> str:
    """Execute a reviewed compatibility shell command through SandboxRunner."""
    try:
        from nexus.sandbox import SandboxRunner

        cwd_path = _resolve_path(cwd) if cwd else _resolve_path("")
        work_dir = str(cwd_path)
        if timeout is not None:
            try:
                timeout = float(timeout)
            except (ValueError, TypeError):
                timeout = 120.0
        result = SandboxRunner(work_dir).run_shell(
            command,
            cwd=work_dir,
            timeout_seconds=timeout,
            network=network,
            require_os_isolation=require_os_isolation,
        )
        return result.format_tool_output()
    except (OSError, RuntimeError, TypeError, ValueError) as e:
        return f"❌ Error running command: {e}"

def tool_run_process(
    argv: list[str],
    cwd: str | None = None,
    timeout: float | int | str = 120,
    network: bool = False,
    require_os_isolation: bool = False,
) -> str:
    """Execute an argv vector without a shell."""
    try:
        from nexus.sandbox import CommandSpec, SandboxRunner

        cwd_path = _resolve_path(cwd) if cwd else _resolve_path("")
        work_dir = str(cwd_path)
        spec = CommandSpec.create(
            argv,
            work_dir,
            timeout_seconds=float(timeout),
            network=network,
            require_os_isolation=require_os_isolation,
        )
        return SandboxRunner(work_dir).run(spec).format_tool_output()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return f"❌ Error running typed process: {exc}"

def tool_process_run(
    command: str,
    cwd: str | None = None,
    network: bool = False,
    require_os_isolation: bool = False,
    timeout: float | int | str = 3600,
    max_output_bytes: int = 1_000_000,
) -> str:
    """Start a sandboxed background process with bounded lifetime and logs."""
    try:
        work_dir = str(_resolve_path(cwd) if cwd else _resolve_path(""))
        argv = shlex.split(command, posix=True)
        if not argv:
            return "❌ Background command is empty"
        timeout_seconds = float(timeout)
        if timeout_seconds <= 0 or timeout_seconds > 86_400:
            return "❌ Background timeout must be between 0 and 86400 seconds"
        max_output_bytes = max(1_024, min(int(max_output_bytes), 20_000_000))
        log_dir = nexus_home() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        run_id = uuid.uuid4().hex
        stdout_log = log_dir / f"bg_{run_id}_stdout.log"
        stderr_log = log_dir / f"bg_{run_id}_stderr.log"

        from nexus.sandbox import CommandSpec, SandboxRunner

        sandbox = SandboxRunner(Path(work_dir))
        safe_env = sandbox._filtered_env({})
        safe_env["NEXUS_SANDBOX"] = "restricted-background"
        spec = CommandSpec.create(
            argv,
            work_dir,
            timeout_seconds=timeout_seconds,
            network=network,
            require_os_isolation=require_os_isolation,
            max_output_bytes=max_output_bytes,
        )
        try:
            prepared = sandbox.prepare(spec)
        except PermissionError as exc:
            return f"❌ BLOCKED: {exc}"

        with stdout_log.open("wb") as stdout_f, stderr_log.open("wb") as stderr_f:
            proc = subprocess.Popen(
                list(prepared.argv),
                shell=False,
                stdout=stdout_f,
                stderr=stderr_f,
                cwd=prepared.cwd,
                env=dict(prepared.env),
                start_new_session=os.name != "nt",
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
                preexec_fn=SandboxRunner._resource_limits_factory(spec) if os.name == "posix" else None,
            )

        record = {
            "command": command,
            "argv": list(prepared.argv),
            "pid": proc.pid,
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
            "started": datetime.now().isoformat(),
            "started_monotonic": time.monotonic(),
            "timeout_seconds": timeout_seconds,
            "max_output_bytes": max_output_bytes,
            "process": proc,
            "process_group": proc.pid,
            "owner": _tool_owner.get(),
            "backend": prepared.backend.value,
            "network_allowed": prepared.network_allowed,
            "network_enforced": prepared.network_enforced,
            "cleanup_path": prepared.cleanup_path,
            "timed_out": False,
            "output_truncated": False,
        }
        with _bg_processes_lock:
            _bg_processes[proc.pid] = record
        threading.Thread(
            target=_watch_background_process,
            args=(proc.pid,),
            name=f"nexus-bg-{proc.pid}",
            daemon=True,
        ).start()

        return (
            f"✅ Background process started\n"
            f"  PID:    {proc.pid}\n"
            f"  CMD:    {command}\n"
            f"  Sandbox: {prepared.backend.value}\n"
            f"  Network: {'on' if network else 'off'} "
            f"({'enforced' if prepared.network_enforced else 'policy-only'})\n"
            f"  Timeout: {timeout_seconds:.1f}s\n"
            f"  Stdout: {stdout_log}\n"
            f"  Stderr: {stderr_log}"
        )
    except (LookupError, OSError, RuntimeError, TypeError, ValueError) as e:
        return f"❌ Error starting background process: {e}"

def tool_process_status(pid: int) -> str:
    """Poll a process started by Nexus and return its unedited logs."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return "❌ PID must be an integer"
    with _bg_processes_lock:
        record = _bg_processes.get(pid)
    if not record:
        return f"❌ PID {pid} is not a Nexus-managed background process"
    proc = record["process"]
    exit_code = proc.poll()
    stdout, stdout_cut = _read_bounded_log(Path(record["stdout_log"]), record["max_output_bytes"])
    stderr, stderr_cut = _read_bounded_log(Path(record["stderr_log"]), record["max_output_bytes"])
    truncated = bool(record.get("output_truncated") or stdout_cut or stderr_cut)
    if record.get("timed_out"):
        state = f"timed out after {record['timeout_seconds']:.1f}s"
        marker = "⏰"
    elif exit_code is None:
        state = "running"
        marker = "✅"
    else:
        state = f"exited ({exit_code})"
        marker = "✅" if exit_code == 0 else "❌"
    return (
        f"{marker} PID {pid} {state}\n"
        f"Command: {record['command']}\n"
        f"Sandbox: {record['backend']}\n"
        f"[stdout]\n{stdout}\n[stderr]\n{stderr}"
        + ("\n[output truncated by Nexus policy]" if truncated else "")
    )

def tool_process_stop(pid: int) -> str:
    """Terminate only a process that Nexus itself started."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return "❌ PID must be an integer"
    with _bg_processes_lock:
        record = _bg_processes.get(pid)
    if not record:
        return f"❌ PID {pid} is not a Nexus-managed background process"
    try:
        _terminate_background_record(record)
        _cleanup_background_record(record)
        with _bg_processes_lock:
            _bg_processes.pop(pid, None)
        return f"✅ Terminated Nexus-managed PID {pid}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"❌ PID {pid} could not be terminated: {exc}"

def _watch_background_process(pid: int) -> None:
    with _bg_processes_lock:
        record = _bg_processes.get(pid)
    if not record:
        return
    process = record["process"]
    try:
        process.wait(timeout=float(record["timeout_seconds"]))
    except subprocess.TimeoutExpired:
        record["timed_out"] = True
        try:
            _terminate_background_record(record)
        except (OSError, subprocess.TimeoutExpired):
            pass
    finally:
        record["output_truncated"] = bool(
            _truncate_log(Path(record["stdout_log"]), int(record["max_output_bytes"]))
            or _truncate_log(Path(record["stderr_log"]), int(record["max_output_bytes"]))
        )
        _cleanup_background_record(record)

def stop_owned_processes(owner: str) -> dict[str, object]:
    """Terminate background processes created by one agent session."""

    stopped: list[int] = []
    errors: list[str] = []
    with _bg_processes_lock:
        records = list(_bg_processes.items())
    for pid, record in records:
        if record.get("owner") != owner:
            continue
        try:
            _terminate_background_record(record)
            stopped.append(pid)
            _cleanup_background_record(record)
            with _bg_processes_lock:
                _bg_processes.pop(pid, None)
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"PID {pid}: {exc}")
    return {"stopped": stopped, "errors": errors}

def stop_all_background_processes() -> dict[str, object]:
    """Best-effort shutdown for every child still owned by this Nexus process."""
    stopped: list[int] = []
    errors: list[str] = []
    with _bg_processes_lock:
        records = list(_bg_processes.items())
    for pid, record in records:
        try:
            _terminate_background_record(record)
            stopped.append(pid)
            _cleanup_background_record(record)
            with _bg_processes_lock:
                _bg_processes.pop(pid, None)
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"PID {pid}: {exc}")
    return {"stopped": stopped, "errors": errors}

