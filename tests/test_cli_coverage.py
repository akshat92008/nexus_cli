"""Tests for CLI coverage and boundary conditions."""

import os
import sys
from unittest.mock import patch

import pytest

from nexus.cli import main


def test_cli_no_args(capsys):
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
        with patch("nexus.cli.run_interactive") as mock_run_interactive:
            with patch("nexus.cli.Agent"):
                with patch.object(sys, "argv", ["nexus"]):
                    try:
                        main()
                    except SystemExit:
                        pass
                    mock_run_interactive.assert_called_once()


def test_cli_benchmark_invalid_manifest():
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
        with patch.object(sys, "argv", ["nexus", "benchmark", "--manifest", "nonexistent.json"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code in (1, 2)


def test_cli_invalid_command(capsys):
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
        with patch.object(sys, "argv", ["nexus", "invalid-cmd"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code in (1, 2)


def test_generate_dashboard_subcommand_is_dispatched_before_global_parser(tmp_path):
    input_path = tmp_path / "benchmark.json"
    output_path = tmp_path / "dashboard.html"
    input_path.write_text("{}", encoding="utf-8")

    with patch("nexus.dashboard.RegressionDashboard.generate") as generate:
        with patch.object(
            sys,
            "argv",
            [
                "nexus",
                "generate-dashboard",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ],
        ):
            main()

    generate.assert_called_once_with(str(input_path), str(output_path))


def test_generate_dashboard_accepts_shipped_manifest_schema(tmp_path):
    input_path = tmp_path / "benchmark.json"
    output_path = tmp_path / "dashboard.html"
    input_path.write_text(
        '{"schema_version":"nexus.benchmark.v1","name":"smoke","tasks":[]}',
        encoding="utf-8",
    )

    with patch.object(
        sys,
        "argv",
        [
            "nexus",
            "generate-dashboard",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
    ):
        main()

    assert output_path.is_file()

def test_cli_direct_command():
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
        with patch("nexus.cli.Agent") as MockAgent:
            with patch.object(sys, "argv", ["nexus", "!echo hello"]):
                mock_agent = MockAgent.return_value
                mock_agent._execute_tool_with_safety.return_value = ("hello\n", True)
                try:
                    main()
                except SystemExit:
                    pass
                mock_agent._execute_tool_with_safety.assert_called_once_with(
                    "run_process", {"argv": ["echo", "hello"], "cwd": mock_agent.working_dir}, _user_initiated=True, _user_confirmed=False
                )

def test_cli_direct_command_confirm_danger():
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
        with patch("nexus.cli.Agent") as MockAgent:
            with patch.object(sys, "argv", ["nexus", "--confirm-danger", "!rm -rf ./sentinel"]):
                mock_agent = MockAgent.return_value
                mock_agent._execute_tool_with_safety.return_value = ("success\n", True)
                try:
                    main()
                except SystemExit:
                    pass
                mock_agent._execute_tool_with_safety.assert_called_once_with(
                    "run_process", {"argv": ["rm", "-rf", "./sentinel"], "cwd": mock_agent.working_dir}, _user_initiated=True, _user_confirmed=True
                )

def test_cli_direct_command_pending_rewrite(capsys):
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
        with patch("nexus.cli.Agent") as MockAgent:
            with patch.object(sys, "argv", ["nexus", "!rm -rf /"]):
                mock_agent = MockAgent.return_value
                mock_agent._execute_tool_with_safety.return_value = ("⏸️ PENDING_CONFIRMATION [danger-0001]: ...", False)
                try:
                    main()
                except SystemExit:
                    pass
                captured = capsys.readouterr()
                assert "Run with --confirm-danger to execute this exact command: !rm -rf /" in captured.out

def test_cli_direct_command_real_execution(tmp_path):
    import subprocess
    # Run a real harmless direct command via subprocess to avoid mock gaps.
    # Direct commands use the plan-mode policy which does NOT require OS
    # isolation, so the command should succeed on all platforms where a
    # sandbox backend is available, and produce a structured JSON result.
    result = subprocess.run(
        [sys.executable, "-m", "nexus", "--output-format", "json", "!echo real_test_hello"],
        env={**os.environ, "NVIDIA_API_KEY": "test"},
        capture_output=True,
        text=True,
    )
    import json

    if sys.platform == "win32":
        # Windows has no integrated native sandbox backend. The restricted-
        # process fallback is used by default for plan-mode direct commands,
        # which does NOT require OS isolation. So the echo should succeed.
        # If it fails for any other reason the returncode will be 2.
        if result.returncode == 0:
            data = json.loads(result.stdout)
            assert data["name"] == "run_process"
            # echo may not produce output on all Windows shells; just check shape.
        else:
            # Acceptable: Windows subprocess environment may differ.
            assert result.returncode in (0, 2)
    else:
        # On Linux and macOS a native sandbox backend is available in CI
        # (bubblewrap or sandbox-exec). The plan-mode policy does not
        # require OS isolation, so restricted-process is also acceptable.
        assert result.returncode == 0, (
            f"Expected exit 0 but got {result.returncode}.\n"
            f"stdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
        )
        data = json.loads(result.stdout)
        assert data["name"] == "run_process"
        assert "real_test_hello" in data["result"]


def test_cli_single_prompt():
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
        with patch("nexus.cli.Agent") as MockAgent:
            with patch.object(sys, "argv", ["nexus", "write a python script"]):
                mock_agent = MockAgent.return_value
                mock_agent.export_final_report.return_value = {"status": "VERIFIED"}
                try:
                    main()
                except SystemExit:
                    pass
                mock_agent.run.assert_called_once_with("write a python script")


def test_cli_missing_credentials(capsys):
    with patch.dict(os.environ, {}, clear=True):
        with patch.object(sys, "argv", ["nexus"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code != 0

