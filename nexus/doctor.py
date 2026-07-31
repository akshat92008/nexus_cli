"""Preflight diagnostics for a Nexus installation."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from nexus import __version__
from nexus.preflight import probe_hosted, probe_ollama
from nexus.sandbox import SandboxBackend, SandboxRunner


@dataclass(frozen=True)
class Diagnostic:
    """One actionable preflight result."""

    name: str
    status: str
    detail: str

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def format(self) -> str:
        marker = {"PASS": "✓", "WARN": "!", "FAIL": "✗"}[self.status]
        return f"[{marker}] {self.name}: {self.detail}"


def _workspace_check(working_dir: Path) -> Diagnostic:
    try:
        working_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=".nexus-doctor-",
            dir=working_dir,
            delete=True,
        ):
            pass
    except OSError as exc:
        return Diagnostic("Workspace", "FAIL", f"not writable: {exc}")
    return Diagnostic("Workspace", "PASS", f"writable at {working_dir}")


def _sandbox_check(root: Path) -> Diagnostic:
    try:
        backend = SandboxRunner(root).backend()
    except (OSError, ValueError) as exc:
        return Diagnostic("Sandbox", "FAIL", f"could not initialize: {exc}")
    if backend == SandboxBackend.RESTRICTED:
        return Diagnostic(
            "Sandbox",
            "WARN",
            "restricted-process fallback; filesystem/network isolation is policy-only",
        )
    return Diagnostic("Sandbox", "PASS", f"native backend: {backend.value}")


def run_doctor(
    working_dir: str | None = None,
    nova_model: str = "nova_codex",
) -> tuple[bool, str]:
    """Run non-destructive installation checks and return success plus report."""
    root = Path(working_dir or os.getcwd()).expanduser().resolve()
    local = probe_ollama(nova_model, use_cache=False)
    hosted = probe_hosted()
    diagnostics = [
        Diagnostic(
            "Nexus",
            "PASS",
            f"version {__version__} on Python {sys.version_info.major}.{sys.version_info.minor}",
        ),
        _workspace_check(root),
        Diagnostic(
            "Git",
            "PASS" if shutil.which("git") else "WARN",
            shutil.which("git") or "git executable not found; non-Git copy mode will be used",
        ),
        _sandbox_check(root),
        Diagnostic(
            "Local Nova",
            "PASS" if local.ready else "WARN",
            local.detail,
        ),
        Diagnostic(
            "Hosted provider",
            "PASS" if hosted.ready else "WARN",
            hosted.detail,
        ),
    ]
    has_backend = local.ready or hosted.ready
    hard_failures = [item for item in diagnostics if item.status == "FAIL"]
    success = not hard_failures and has_backend
    lines = [f"Nexus doctor — {'READY' if success else 'ACTION REQUIRED'}", ""]
    lines.extend(item.format() for item in diagnostics)
    if not has_backend:
        lines.extend(
            [
                "",
                "Configure at least one backend:",
                f"  local: start Ollama and install '{nova_model}'",
                "  hosted: set NVIDIA_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY",
                "  custom: set NEXUS_OPENAI_BASE_URL and NEXUS_OPENAI_API_KEY",
            ]
        )
    if local.ready and hosted.ready:
        lines.extend(
            [
                "",
                "Nova is optional. Hosted runs can use --local-intern off, while",
                "--local-intern auto uses Nova only when it is available.",
            ]
        )
    return success, "\n".join(lines)
