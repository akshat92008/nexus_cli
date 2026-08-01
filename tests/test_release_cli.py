"""Release-facing CLI behavior and diagnostics."""

from __future__ import annotations

import io
import subprocess
import sys
import urllib.error
from pathlib import Path

from nexus.cli import _configure_output_streams, non_interactive_exit_code
from nexus.doctor import run_doctor
from nexus.nova_runtime import OllamaClient
from nexus.webapp.server import _is_allowed_web_origin, _is_sensitive_path
from scripts import run_release_gate


def test_non_interactive_failure_uses_nonzero_exit_code():
    assert non_interactive_exit_code("Nova backend error: Ollama unavailable", []) == 2
    assert (
        non_interactive_exit_code(
            "Pending edit",
            [{"type": "tool_call", "success": False}],
        )
        == 2
    )


def test_non_interactive_success_uses_zero_exit_code():
    assert (
        non_interactive_exit_code(
            "Implemented and verified.",
            [{"type": "tool_call", "success": True}],
        )
        == 0
    )


def test_doctor_accepts_hosted_backend_when_ollama_is_offline(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def offline(*_args, **_kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    success, report = run_doctor(str(tmp_path))
    assert success
    assert "READY" in report
    assert "Local Nova" in report
    assert "Hosted provider" in report


def test_module_entrypoint_exposes_version():
    result = subprocess.run(
        [sys.executable, "-m", "nexus", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "NexusAI 3.1.1"


def test_ollama_host_without_scheme_is_normalized(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11434/")
    client = OllamaClient()
    assert client.base_url == "http://127.0.0.1:11434"


def test_web_file_api_classifies_secret_paths(tmp_path):
    assert _is_sensitive_path(tmp_path / ".env")
    assert _is_sensitive_path(tmp_path / ".env.production")
    assert _is_sensitive_path(tmp_path / ".git" / "config")
    assert _is_sensitive_path(tmp_path / ".nexusai" / "evidence.jsonl")
    assert not _is_sensitive_path(tmp_path / ".github" / "workflows" / "ci.yml")
    assert not _is_sensitive_path(tmp_path / "src" / "main.py")


def test_websocket_origin_is_limited_to_loopback():
    assert _is_allowed_web_origin(None)
    assert _is_allowed_web_origin("http://localhost:3000")
    assert _is_allowed_web_origin("http://127.0.0.1:8080")
    assert not _is_allowed_web_origin("https://attacker.example")
    assert not _is_allowed_web_origin("file://localhost/tmp/index.html")


def test_release_gate_uses_uv_when_managed_venv_has_no_pip(monkeypatch):
    monkeypatch.setattr(run_release_gate.importlib.util, "find_spec", lambda _name: None)
    monkeypatch.setattr(run_release_gate.shutil, "which", lambda _name: "/tools/uv")

    command = run_release_gate.wheel_install_command(
        "/venv/python", Path("/target"), Path("/dist/nexus.whl")
    )

    assert command == [
        "/tools/uv",
        "pip",
        "install",
        "--python",
        "/venv/python",
        "--no-deps",
        "--target",
        str(Path("/target")),
        str(Path("/dist/nexus.whl")),
    ]


def test_release_gate_prefers_pip_when_available(monkeypatch):
    monkeypatch.setattr(run_release_gate.importlib.util, "find_spec", lambda _name: object())

    command = run_release_gate.wheel_install_command(
        "/venv/python", Path("/target"), Path("/dist/nexus.whl")
    )

    assert command[:4] == ["/venv/python", "-m", "pip", "install"]


def test_cli_reconfigures_legacy_output_streams_to_utf8():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")

    _configure_output_streams((stream,))
    stream.write("✓")
    stream.flush()

    assert stream.encoding.lower().replace("-", "") == "utf8"
    assert raw.getvalue() == "✓".encode()
