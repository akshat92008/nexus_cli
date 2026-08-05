"""Universal gateway for all external process execution.

Enforces network policies, environment filtering, isolation, output limits, and cleanup.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from nexus.sandbox import CommandSpec, SandboxRunner, CommandResult, PreparedCommand


@dataclass(frozen=True)
class ProcessRequest:
    """A high-level request to execute an external process."""
    purpose: str
    command: tuple[str, ...]
    workspace: str | Path
    trust_level: str = "repository_controlled"
    network_policy: str = "deny"
    isolation_policy: str = "required"
    environment_policy: str = "filtered"
    timeout_seconds: float = 120.0
    output_limit_bytes: int = 1_000_000
    allowed_sensitive_env_keys: tuple[str, ...] = ()
    env_additions: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        purpose: str,
        command: list[str] | tuple[str, ...],
        workspace: str | Path,
        *,
        trust_level: str = "repository_controlled",
        network_policy: str = "deny",
        isolation_policy: str = "required",
        environment_policy: str = "filtered",
        timeout_seconds: float = 120.0,
        output_limit_bytes: int = 1_000_000,
        allowed_sensitive_env_keys: tuple[str, ...] = (),
        env_additions: Mapping[str, str] | None = None,
    ) -> "ProcessRequest":
        return cls(
            purpose=purpose,
            command=tuple(command),
            workspace=workspace,
            trust_level=trust_level,
            network_policy=network_policy,
            isolation_policy=isolation_policy,
            environment_policy=environment_policy,
            timeout_seconds=timeout_seconds,
            output_limit_bytes=output_limit_bytes,
            allowed_sensitive_env_keys=tuple(allowed_sensitive_env_keys),
            env_additions=dict(env_additions or {})
        )

class ManagedProcess:
    """A background process wrapped for safe termination and group cleanup."""

    def __init__(self, process: subprocess.Popen, prepared: PreparedCommand):
        self._process = process
        self.prepared = prepared
        self.pid = process.pid

    @property
    def stdout(self):
        return self._process.stdout

    @property
    def stderr(self):
        return self._process.stderr

    @property
    def returncode(self) -> int | None:
        return self._process.returncode

    def poll(self) -> int | None:
        return self._process.poll()

    def wait(self, timeout: float | None = None) -> int:
        return self._process.wait(timeout=timeout)

    def terminate(self) -> None:
        """Safely terminate the process and its process group."""
        if self._process.poll() is not None:
            return
        try:
            if os.name == "posix":
                import signal
                os.killpg(self._process.pid, signal.SIGTERM)
            else:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self._process.pid)],
                    capture_output=True,
                )
        except OSError:
            pass

    def kill(self) -> None:
        """Force kill the process and its process group."""
        if self._process.poll() is not None:
            return
        try:
            if os.name == "posix":
                import signal
                os.killpg(self._process.pid, signal.SIGKILL)
            else:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self._process.pid)],
                    capture_output=True,
                )
        except OSError:
            pass

class ProcessExecutionGateway:
    """The central authority for executing processes in Nexus."""

    @classmethod
    def _build_sandbox_spec(cls, request: ProcessRequest) -> CommandSpec:
        require_os_isolation = request.isolation_policy == "required"
        network = request.network_policy == "allow"
        
        env = dict(request.env_additions)
        if request.environment_policy == "forward_all":
            env = {**os.environ, **env}
            
        return CommandSpec.create(
            argv=request.command,
            cwd=request.workspace,
            timeout_seconds=request.timeout_seconds,
            network=network,
            env=env,
            max_output_bytes=request.output_limit_bytes,
            require_os_isolation=require_os_isolation,
            allowed_sensitive_env_keys=request.allowed_sensitive_env_keys,
        )

    @classmethod
    def run(cls, request: ProcessRequest) -> CommandResult:
        """Run a process synchronously and return the result."""
        spec = cls._build_sandbox_spec(request)
        runner = SandboxRunner(request.workspace)
        return runner.run(spec)

    @classmethod
    def popen(cls, request: ProcessRequest, **kwargs) -> ManagedProcess:
        """Start a long-running process (e.g. LSP) in the sandbox."""
        spec = cls._build_sandbox_spec(request)
        runner = SandboxRunner(request.workspace)
        prepared = runner.prepare(spec)
        
        popen_kwargs = {
            "cwd": prepared.cwd,
            "env": prepared.env,
        }
        popen_kwargs.update(kwargs)
        
        if os.name == "posix":
            popen_kwargs.setdefault("start_new_session", True)
            popen_kwargs.setdefault("preexec_fn", SandboxRunner._resource_limits_factory(spec))
        elif os.name == "nt":
            popen_kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512))
            
        process = subprocess.Popen(list(prepared.argv), **popen_kwargs)
        return ManagedProcess(process, prepared)
