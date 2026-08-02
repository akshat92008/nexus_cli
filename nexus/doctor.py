"""Preflight diagnostics for a Nexus installation."""

from __future__ import annotations

import os
import platform
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


# Modes that require a native OS sandbox to operate. A missing sandbox in
# these modes is a hard operational failure, not merely advisory.
_ISOLATION_REQUIRED_MODES = frozenset(
    {"workspace", "autonomous", "quality", "budget", "local-only", "ci"}
)

_SANDBOX_INSTALL_HINT: dict[str, str] = {
    "linux": (
        "Install bubblewrap:\n"
        "    sudo apt-get install bubblewrap        # Debian / Ubuntu\n"
        "    sudo dnf install bubblewrap            # Fedora / RHEL\n"
        "    sudo pacman -S bubblewrap              # Arch\n"
        "  Then re-run: nexus --doctor"
    ),
    "darwin": (
        "sandbox-exec is shipped with macOS. If this check fails, your macOS "
        "installation may be incomplete. Try: xcode-select --install"
    ),
    "windows": (
        "Windows does not have an integrated native sandbox backend. "
        "Autonomous, quality, budget, local-only, and CI modes will fail "
        "closed on Windows. Use plan or review mode, or run in WSL2 with "
        "bubblewrap installed."
    ),
}


def _sandbox_check(root: Path, mode: str = "review") -> Diagnostic:
    try:
        backend = SandboxRunner(root).backend()
    except (OSError, ValueError) as exc:
        return Diagnostic("Sandbox", "FAIL", f"could not initialize: {exc}")

    if backend != SandboxBackend.RESTRICTED:
        return Diagnostic("Sandbox", "PASS", f"native backend: {backend.value}")

    # Restricted-process fallback — assess severity by requested mode.
    system = platform.system().lower()
    install_hint = _SANDBOX_INSTALL_HINT.get(system, "Install a supported sandbox backend.")

    if mode in _ISOLATION_REQUIRED_MODES:
        return Diagnostic(
            "Sandbox",
            "FAIL",
            (
                f"No native OS sandbox available (got: restricted-process).\n"
                f"  Modes that require isolation — {', '.join(sorted(_ISOLATION_REQUIRED_MODES))} — "
                f"will be blocked.\n  {install_hint}"
            ),
        )

    # plan / direct-command modes do not require OS isolation.
    return Diagnostic(
        "Sandbox",
        "WARN",
        (
            "restricted-process fallback; filesystem/network isolation is policy-only.\n"
            f"  To enable full isolation: {install_hint}"
        ),
    )


def run_doctor(
    working_dir: str | None = None,
    nova_model: str = "nova_codex",
    mode: str = "review",
) -> tuple[bool, str]:
    """Run non-destructive installation checks and return success plus report."""
    root = Path(working_dir or os.getcwd()).expanduser().resolve()
    local = probe_ollama(nova_model, use_cache=False)
    hosted = probe_hosted()
    sandbox_diag = _sandbox_check(root, mode=mode)
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
        sandbox_diag,
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
    if hard_failures:
        lines.extend(
            [
                "",
                "ACTION REQUIRED — the issues marked [✗] above prevent normal operation.",
                "Fix them and re-run: nexus --doctor",
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
