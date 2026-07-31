"""Tests for CLI coverage and boundary conditions."""

import os
import sys
from unittest.mock import patch
import pytest

from nexus.cli import main

def test_cli_no_args(capsys):
    with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
        with patch("nexus.cli.run_interactive") as mock_run_interactive:
            with patch("nexus.cli.Agent") as mock_agent:
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
