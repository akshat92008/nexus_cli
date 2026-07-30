"""Typed, policy-driven command execution for Nexus.

The legacy shell tool remains available for compatibility, but autonomous
workflows use :class:`SandboxRunner` with an argv vector.  The runner selects
the strongest native isolation backend available on the host:

* Bubblewrap on Linux
* ``sandbox-exec`` on macOS
* a restricted subprocess fallback on other hosts

The fallback is deliberately visible in every result.  Callers may set
``require_os_isolation`` to fail closed instead of silently running without a
kernel-enforced filesystem/network boundary.
"""

from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on Windows
    resource = None


class SandboxBackend(str, Enum):
    """Execution backend selected for a command."""

    BUBBLEWRAP = "bubblewrap"
    MACOS = "sandbox-exec"
    RESTRICTED = "restricted-process"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CommandSpec:
    """A shell-free command request."""

    argv: tuple[str, ...]
    cwd: str
    timeout_seconds: float = 120.0
    network: bool = False
    env: Mapping[str, str] = field(default_factory=dict)
    max_output_bytes: int = 1_000_000
    require_os_isolation: bool = False

    @classmethod
    def create(
        cls,
        argv: Sequence[str],
        cwd: str | Path,
        *,
        timeout_seconds: float = 120.0,
        network: bool = False,
        env: Mapping[str, str] | None = None,
        max_output_bytes: int = 1_000_000,
        require_os_isolation: bool = False,
    ) -> "CommandSpec":
        normalized = tuple(str(item) for item in argv)
        if not normalized or not normalized[0].strip():
            raise ValueError("argv must contain an executable")
        timeout = float(timeout_seconds)
        if timeout <= 0:
            raise ValueError("timeout_seconds must be positive")
        return cls(
            argv=normalized,
            cwd=str(Path(cwd).expanduser().resolve()),
            timeout_seconds=timeout,
            network=bool(network),
            env=dict(env or {}),
            max_output_bytes=max(1_024, int(max_output_bytes)),
            require_os_isolation=bool(require_os_isolation),
        )


@dataclass
class CommandResult:
    """Machine-readable result from a command sandbox."""

    argv: list[str]
    cwd: str
    backend: SandboxBackend
    success: bool
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    blocked_reason: str = ""
    duration_ms: int = 0
    network_allowed: bool = False
    network_enforced: bool = False
    output_truncated: bool = False

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["backend"] = self.backend.value
        return payload

    def format_tool_output(self) -> str:
        command = shlex.join(self.argv)
        if self.backend == SandboxBackend.BLOCKED:
            return f"❌ BLOCKED: {self.blocked_reason}\n$ {command}"
        if self.timed_out:
            return (
                f"⏰ Command timed out after {self.duration_ms / 1000:.1f}s "
                f"[sandbox={self.backend.value}]\n$ {command}"
            )
        marker = "✅" if self.success else f"❌ (exit code {self.exit_code})"
        if self.network_enforced:
            network_status = "on" if self.network_allowed else "off"
        else:
            network_status = "policy-only"
        chunks = [
            f"{marker} $ {command}",
            (
                f"[sandbox={self.backend.value} network="
                f"{network_status} duration_ms={self.duration_ms}]"
            ),
        ]
        if self.stdout:
            chunks.append(self.stdout)
        if self.stderr:
            chunks.append(f"[stderr]\n{self.stderr}")
        if not self.stdout and not self.stderr:
            chunks.append("(no output)")
        if self.output_truncated:
            chunks.append("[output truncated by Nexus policy]")
        return "\n".join(chunks)


class SandboxRunner:
    """Execute typed commands inside the strongest available host sandbox."""

    _backend_cache: SandboxBackend | None = None

    SAFE_ENV_KEYS = {
        "PATH",
        "LANG",
        "LC_ALL",
        "TZ",
        "TMPDIR",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "PYTHONPATH",
        "NODE_PATH",
        "JAVA_HOME",
        "GOROOT",
        "GOPATH",
        "CARGO_HOME",
        "RUSTUP_HOME",
    }

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).expanduser().resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"Sandbox workspace does not exist: {self.workspace}")

    def backend(self) -> SandboxBackend:
        if self._backend_cache is not None:
            return self._backend_cache
        system = platform.system().lower()
        selected = SandboxBackend.RESTRICTED
        if system == "linux" and shutil.which("bwrap") and self._probe_bubblewrap():
            selected = SandboxBackend.BUBBLEWRAP
        elif (
            system == "darwin"
            and shutil.which("sandbox-exec")
            and self._probe_macos_sandbox()
        ):
            selected = SandboxBackend.MACOS
        type(self)._backend_cache = selected
        return selected

    def run(self, spec: CommandSpec) -> CommandResult:
        cwd = Path(spec.cwd).expanduser().resolve()
        try:
            cwd.relative_to(self.workspace)
        except ValueError:
            return self._blocked(spec, "Command cwd is outside the authorized workspace")
        if not cwd.is_dir():
            return self._blocked(spec, f"Command cwd does not exist: {cwd}")

        backend = self.backend()
        if spec.require_os_isolation and backend == SandboxBackend.RESTRICTED:
            return self._blocked(
                spec,
                "No supported OS sandbox is available; install bubblewrap on Linux "
                "or use sandbox-exec on macOS",
            )

        env = self._filtered_env(spec.env)
        command = list(spec.argv)
        cleanup_path: Path | None = None
        if backend == SandboxBackend.BUBBLEWRAP:
            command = self._bubblewrap_command(spec, cwd)
        elif backend == SandboxBackend.MACOS:
            command, cleanup_path = self._macos_command(spec, cwd)

        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=False,
                timeout=spec.timeout_seconds,
                shell=False,
                preexec_fn=self._resource_limits if os.name == "posix" else None,
            )
            duration = int((time.monotonic() - started) * 1000)
            stdout, stdout_cut = self._decode_bounded(
                completed.stdout or b"", spec.max_output_bytes
            )
            stderr, stderr_cut = self._decode_bounded(
                completed.stderr or b"", spec.max_output_bytes
            )
            return CommandResult(
                argv=list(spec.argv),
                cwd=str(cwd),
                backend=backend,
                success=completed.returncode == 0,
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration,
                network_allowed=spec.network,
                network_enforced=backend != SandboxBackend.RESTRICTED,
                output_truncated=stdout_cut or stderr_cut,
            )
        except subprocess.TimeoutExpired as exc:
            duration = int((time.monotonic() - started) * 1000)
            stdout, stdout_cut = self._decode_bounded(
                self._as_bytes(exc.stdout), spec.max_output_bytes
            )
            stderr, stderr_cut = self._decode_bounded(
                self._as_bytes(exc.stderr), spec.max_output_bytes
            )
            return CommandResult(
                argv=list(spec.argv),
                cwd=str(cwd),
                backend=backend,
                success=False,
                exit_code=None,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
                duration_ms=duration,
                network_allowed=spec.network,
                network_enforced=backend != SandboxBackend.RESTRICTED,
                output_truncated=stdout_cut or stderr_cut,
            )
        except OSError as exc:
            return CommandResult(
                argv=list(spec.argv),
                cwd=str(cwd),
                backend=backend,
                success=False,
                exit_code=None,
                stderr=str(exc),
                duration_ms=int((time.monotonic() - started) * 1000),
                network_allowed=spec.network,
                network_enforced=backend != SandboxBackend.RESTRICTED,
            )
        finally:
            if cleanup_path is not None:
                cleanup_path.unlink(missing_ok=True)

    def run_shell(
        self,
        command: str,
        *,
        cwd: str | Path | None = None,
        timeout_seconds: float = 120.0,
        network: bool = False,
        require_os_isolation: bool = False,
    ) -> CommandResult:
        """Compatibility path for a reviewed shell string."""
        shell = "/bin/sh" if os.name != "nt" else "cmd.exe"
        argv = (
            [shell, "-c", command]
            if os.name != "nt"
            else [shell, "/d", "/s", "/c", command]
        )
        result = self.run(
            CommandSpec.create(
                argv,
                cwd or self.workspace,
                timeout_seconds=timeout_seconds,
                network=network,
                require_os_isolation=require_os_isolation,
            )
        )
        try:
            result.argv = shlex.split(command, posix=os.name != "nt")
        except ValueError:
            result.argv = [command]
        return result

    def _bubblewrap_command(self, spec: CommandSpec, cwd: Path) -> list[str]:
        command = [
            "bwrap",
            "--die-with-parent",
            "--new-session",
            "--unshare-user",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/bin",
            "/bin",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind",
            "/lib64",
            "/lib64",
            "--ro-bind",
            "/etc/alternatives",
            "/etc/alternatives",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
        ]
        try:
            self.workspace.relative_to(Path(tempfile.gettempdir()).resolve())
        except ValueError:
            command.extend(["--tmpfs", "/tmp"])
        command.extend(
            [
            "--bind",
            str(self.workspace),
            str(self.workspace),
            "--chdir",
            str(cwd),
            "--setenv",
            "HOME",
            str(self.workspace),
            ]
        )
        if not spec.network:
            command.append("--unshare-net")
        return [*command, "--", *spec.argv]

    def _macos_command(self, spec: CommandSpec, cwd: Path) -> tuple[list[str], Path]:
        workspace = str(self.workspace).replace('"', '\\"')
        temp_dir = tempfile.gettempdir().replace('"', '\\"')
        rules = [
            "(version 1)",
            "(deny default)",
            "(allow process*)",
            "(allow sysctl-read)",
            "(allow mach-lookup)",
            "(allow ipc-posix-shm)",
            "(allow file-read*)",
            f'(allow file-write* (subpath "{workspace}") (subpath "{temp_dir}"))',
            '(allow file-write-data (literal "/dev/null") (literal "/dev/zero"))',
        ]
        if spec.network:
            rules.append("(allow network*)")
        fd, raw_path = tempfile.mkstemp(prefix="nexus-sandbox-", suffix=".sb")
        os.close(fd)
        profile = Path(raw_path)
        profile.write_text("\n".join(rules) + "\n", encoding="utf-8")
        return ["sandbox-exec", "-f", str(profile), *spec.argv], profile

    def _filtered_env(self, additions: Mapping[str, str]) -> dict[str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key in self.SAFE_ENV_KEYS or key.startswith("NEXUS_")
        }
        for key, value in additions.items():
            normalized = str(key)
            if not normalized or "=" in normalized or "\x00" in normalized:
                raise ValueError(f"Invalid environment key: {key!r}")
            env[normalized] = str(value)
        env.update(
            {
                "CI": "true",
                "PAGER": "cat",
                "DEBIAN_FRONTEND": "noninteractive",
                "TERM": "dumb",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                "NEXUS_SANDBOX": "1",
            }
        )
        return env

    @staticmethod
    def _probe_bubblewrap() -> bool:
        """Reject installed-but-unusable bubblewrap binaries before a real task."""
        try:
            result = subprocess.run(
                [
                    "bwrap",
                    "--die-with-parent",
                    "--new-session",
                    "--unshare-user",
                    "--unshare-pid",
                    "--ro-bind",
                    "/",
                    "/",
                    "--proc",
                    "/proc",
                    "--dev",
                    "/dev",
                    "--",
                    "/bin/true",
                ],
                capture_output=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    @staticmethod
    def _probe_macos_sandbox() -> bool:
        try:
            result = subprocess.run(
                ["sandbox-exec", "-p", "(version 1) (allow default)", "/usr/bin/true"],
                capture_output=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    @staticmethod
    def _resource_limits() -> None:
        """Apply conservative limits before ``exec`` on POSIX."""
        if resource is None:
            return
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (512, 512))
        resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024 * 1024, 512 * 1024 * 1024))

    @staticmethod
    def _decode_bounded(value: bytes, limit: int) -> tuple[str, bool]:
        truncated = len(value) > limit
        chosen = value[:limit]
        return chosen.decode("utf-8", errors="replace").rstrip(), truncated

    @staticmethod
    def _as_bytes(value: bytes | str | None) -> bytes:
        if value is None:
            return b""
        return value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")

    @staticmethod
    def _blocked(spec: CommandSpec, reason: str) -> CommandResult:
        return CommandResult(
            argv=list(spec.argv),
            cwd=spec.cwd,
            backend=SandboxBackend.BLOCKED,
            success=False,
            exit_code=None,
            blocked_reason=reason,
            network_allowed=spec.network,
        )
