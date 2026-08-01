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
    assert "smoke" in output_path.read_text(encoding="utf-8")
