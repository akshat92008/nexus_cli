"""Preflight diagnostics for a Nexus installation."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from nexus import __version__


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


def _ollama_check(model: str, base_url: str) -> Diagnostic:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/tags",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return Diagnostic(
            "Local Nova",
            "WARN",
            f"Ollama unavailable at {base_url}: {exc}",
        )
    names = {
        str(item.get("name", "")).split(":", 1)[0]
        for item in payload.get("models", [])
        if isinstance(item, dict)
    }
    requested = model.split(":", 1)[0]
    if requested not in names:
        return Diagnostic(
            "Local Nova",
            "WARN",
            f"Ollama is running, but model '{model}' is not installed",
        )
    return Diagnostic("Local Nova", "PASS", f"Ollama model '{model}' is available")


def run_doctor(
    working_dir: str | None = None,
    nova_model: str = "nova_codex",
) -> tuple[bool, str]:
    """Run non-destructive installation checks and return success plus report."""
    root = Path(working_dir or os.getcwd()).expanduser().resolve()
    ollama_url = (
        os.environ.get("NEXUS_OLLAMA_URL")
        or os.environ.get("OLLAMA_HOST")
        or "http://127.0.0.1:11434"
    )
    if not ollama_url.startswith(("http://", "https://")):
        ollama_url = f"http://{ollama_url}"
    ollama_url = ollama_url.rstrip("/")
    hosted_keys = [
        name
        for name in (
            "NVIDIA_API_KEY",
            "GROQ_API_KEY",
            "OPENROUTER_API_KEY",
        )
        if os.environ.get(name)
    ]
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
            shutil.which("git") or "git executable not found",
        ),
        _ollama_check(nova_model, ollama_url),
        Diagnostic(
            "Hosted provider",
            "PASS" if hosted_keys else "WARN",
            (
                "configured via " + ", ".join(hosted_keys)
                if hosted_keys
                else "no NVIDIA, Groq, or OpenRouter API key configured"
            ),
        ),
    ]
    has_backend = diagnostics[3].passed or bool(hosted_keys)
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
                "  hosted: set NVIDIA_API_KEY (or a supported fallback key)",
            ]
        )
    return success, "\n".join(lines)
