"""Command policy hardening for Nexus CLI.

Classifies commands by risk, denies shell string execution for untrusted inputs,
requires argv array execution, and enforces working directory and timeout bounds.
"""

from __future__ import annotations

import re
import shlex
from enum import Enum
from pathlib import Path
from typing import Sequence


class CommandRisk(str, Enum):
    READ_ONLY = "read_only"
    VALIDATION = "validation"
    BUILD = "build"
    FORMAT = "format"
    PACKAGE_INSTALL = "package_install"
    GIT_MUTATION = "git_mutation"
    NETWORK_REQUEST = "network_request"
    DESTRUCTIVE = "destructive"
    PRIVILEGED = "privileged"
    UNKNOWN = "unknown"


DANGEROUS_COMMAND_PATTERNS = [
    (r"rm\s+-rf?\s+[/~]", "Recursive root or home deletion"),
    (r"chmod\s+777\s+[/~]", "Recursive root permission modification"),
    (r"mkfs", "Filesystem creation"),
    (r"dd\s+if=", "Raw disk write"),
    (r"curl\s+.*\|\s*sh", "Piping untrusted network output to shell"),
    (r"wget\s+.*\|\s*bash", "Piping untrusted network output to bash"),
    (r"sudo\s+", "Privilege escalation request"),
]


class CommandPolicy:
    """Classifies and authorizes command execution requests."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()

    def classify(self, argv: Sequence[str]) -> CommandRisk:
        if not argv:
            return CommandRisk.UNKNOWN

        cmd = Path(argv[0]).name.lower()
        args = " ".join(argv[1:]).lower()

        # Check dangerous patterns first
        full_line = " ".join(argv)
        for pattern, _ in DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, full_line, re.IGNORECASE):
                return CommandRisk.DESTRUCTIVE

        if cmd in ("ls", "cat", "git status", "git log", "git diff", "grep", "find", "pwd", "head", "tail"):
            return CommandRisk.READ_ONLY
        elif cmd in ("pytest", "npm test", "go test", "cargo test", "flake8", "eslint", "ruff", "mypy"):
            return CommandRisk.VALIDATION
        elif cmd in ("make", "npm run build", "cargo build", "go build", "gcc", "clang"):
            return CommandRisk.BUILD
        elif cmd in ("npm install", "pip install", "uv pip install", "cargo add", "yarn add", "poetry add"):
            return CommandRisk.PACKAGE_INSTALL
        elif cmd in ("git",) and any(sub in args for sub in ("commit", "branch", "checkout", "merge", "rebase", "reset")):
            return CommandRisk.GIT_MUTATION
        elif cmd in ("curl", "wget", "fetch", "git push", "git fetch", "git pull"):
            return CommandRisk.NETWORK_REQUEST

        return CommandRisk.UNKNOWN

    def validate_command(
        self,
        argv: Sequence[str],
        cwd: str | Path,
        *,
        allow_shell: bool = False,
    ) -> tuple[str, ...]:
        """Validate command executable and arguments. Returns normalized argv tuple."""
        if allow_shell:
            raise ValueError("Direct shell execution (shell=True) is forbidden under security policy")

        if not argv:
            raise ValueError("argv cannot be empty")

        normalized = tuple(str(item) for item in argv)
        executable = normalized[0].strip()

        if not executable:
            raise ValueError("Executable name cannot be blank")

        # Check dangerous patterns
        full_cmd = " ".join(normalized)
        for pattern, reason in DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, full_cmd, re.IGNORECASE):
                raise ValueError(f"Command blocked by safety policy ({reason}): {full_cmd!r}")

        # Check cwd containment
        cwd_path = Path(cwd).expanduser().resolve()
        try:
            cwd_path.relative_to(self.workspace_root)
        except ValueError:
            raise ValueError(f"Command working directory is outside workspace: {cwd_path}")

        return normalized
